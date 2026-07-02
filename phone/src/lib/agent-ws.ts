/**
 * Agent WebSocket client — connects to the cloud runtime, sends frames,
 * and emits events as they arrive. Reconnects with backoff.
 *
 * The phone UI consumes events via the onEvent callback. The phone sends
 * frames via send(). The client handles ping/pong keepalive automatically.
 */

import { IncomingEvent, OutgoingFrame } from './types';

type Listener = (evt: IncomingEvent) => void;
type StatusListener = (status: ConnStatus) => void;

export type ConnStatus =
  | 'disconnected'
  | 'connecting'
  | 'handshaking'
  | 'connected'
  | 'reconnecting'
  | 'error';

export interface AgentWSOptions {
  url: string;
  channelSecret: string;
  sessionConfig: { base_url: string; api_key: string; model: string };
  resumeSessionId?: string | null;
  onEvent: Listener;
  onStatus: StatusListener;
}

export class AgentWS {
  private ws: WebSocket | null = null;
  private opts: AgentWSOptions;
  private reconnectAttempts = 0;
  private closed = false;
  private keepaliveTimer: ReturnType<typeof setInterval> | null = null;
  private status: ConnStatus = 'disconnected';

  constructor(opts: AgentWSOptions) {
    this.opts = opts;
  }

  connect() {
    if (this.ws && (this.status === 'connecting' || this.status === 'connected')) return;
    this.closed = false;
    this.setStatus(this.reconnectAttempts === 0 ? 'connecting' : 'reconnecting');

    try {
      this.ws = new WebSocket(this.opts.url);
    } catch (e: any) {
      this.setStatus('error');
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.setStatus('handshaking');
      // Send the session.start frame
      this.sendRaw({
        type: 'session.start',
        channel_secret: this.opts.channelSecret,
        session: this.opts.sessionConfig,
        resume_session_id: this.opts.resumeSessionId ?? null,
      });
      // Start keepalive
      this.keepaliveTimer = setInterval(() => {
        this.sendRaw({ type: 'ping' });
      }, 30_000);
    };

    this.ws.onmessage = (e: MessageEvent) => {
      try {
        const evt = JSON.parse(typeof e.data === 'string' ? e.data : '') as IncomingEvent;
        if (evt.type === 'session.start') {
          this.setStatus('connected');
          this.reconnectAttempts = 0;
        }
        this.opts.onEvent(evt);
      } catch (err) {
        console.warn('Failed to parse WS message:', err);
      }
    };

    this.ws.onerror = () => {
      this.setStatus('error');
    };

    this.ws.onclose = () => {
      if (this.keepaliveTimer) {
        clearInterval(this.keepaliveTimer);
        this.keepaliveTimer = null;
      }
      if (!this.closed) {
        this.scheduleReconnect();
      } else {
        this.setStatus('disconnected');
      }
    };
  }

  private scheduleReconnect() {
    if (this.closed) return;
    this.reconnectAttempts++;
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30_000);
    this.setStatus('reconnecting');
    setTimeout(() => {
      if (!this.closed) this.connect();
    }, delay);
  }

  send(frame: OutgoingFrame) {
    if (this.status !== 'connected' && this.status !== 'handshaking') {
      console.warn('Cannot send: not connected (status=' + this.status + ')');
      return false;
    }
    this.sendRaw(frame);
    return true;
  }

  private sendRaw(frame: OutgoingFrame) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(JSON.stringify(frame));
    } catch (e) {
      console.warn('WS send failed:', e);
    }
  }

  close() {
    this.closed = true;
    if (this.keepaliveTimer) {
      clearInterval(this.keepaliveTimer);
      this.keepaliveTimer = null;
    }
    if (this.ws) {
      try { this.ws.close(); } catch {}
      this.ws = null;
    }
    this.setStatus('disconnected');
  }

  getStatus(): ConnStatus { return this.status; }

  private setStatus(s: ConnStatus) {
    this.status = s;
    this.opts.onStatus(s);
  }
}
