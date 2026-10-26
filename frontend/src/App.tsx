import { FormEvent, useEffect, useRef, useState } from "react";
import { getBookings, getHealth, sendChat } from "./api";
import type { Booking, HealthResponse, SourceRef, UiMessage } from "./types";

const starterMessage: UiMessage = {
  id: "welcome",
  role: "assistant",
  text: "Hi, I am ClinicPilot AI. Ask about a clinic, doctor, or treatment, check your appointments, or book a visit. I am an appointment assistant, not a diagnostic service.",
};

const demoPrompts = [
  "What are Metro Care's opening hours?",
  "I have a skin rash. Which doctor do you recommend?",
  "When is my next appointment?",
];

function formatTime(value: string): string {
  return value.slice(0, 5);
}

function SourceChips({ sources }: { sources: SourceRef[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="source-list" aria-label="Grounded sources">
      {sources.map((source) => (
        <span className="source-chip" key={`${source.type}-${source.id}`}>
          {source.type} · {source.id}
        </span>
      ))}
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState<UiMessage[]>([starterMessage]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastIntent, setLastIntent] = useState("idle");
  const [lastState, setLastState] = useState("idle");
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  async function refreshBookings() {
    setIsRefreshing(true);
    try {
      setBookings(await getBookings());
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load bookings");
    } finally {
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    void refreshBookings();
    void getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSending) return;

    const userMessage: UiMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: trimmed,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsSending(true);
    setError(null);

    try {
      const response = await sendChat(trimmed, conversationId);
      setConversationId(response.conversation_id);
      setLastIntent(response.intent);
      setLastState(response.state);
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          text: response.message,
          intent: response.intent,
          sources: response.sources,
          mode: response.llm_mode,
        },
      ]);
      await refreshBookings();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "The assistant request failed",
      );
    } finally {
      setIsSending(false);
    }
  }

  function startNewConversation() {
    setConversationId(null);
    setMessages([starterMessage]);
    setLastIntent("idle");
    setLastState("idle");
    setError(null);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">AI CLINIC WORKBENCH</div>
          <h1>ClinicPilot AI</h1>
          <p>Grounded recommendations and appointment booking for Patient P001.</p>
        </div>
        <div className="header-actions">
          <span className={`mode-pill ${health?.llm_mode === "live" ? "live" : ""}`}>
            {health?.llm_mode === "live" ? "Live model" : "Mock model"}
          </span>
          <button className="button secondary" type="button" onClick={startNewConversation}>
            New conversation
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}

      <section className="workspace-grid">
        <article className="panel chat-panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">CONVERSATION</div>
              <h2>Clinic assistant</h2>
            </div>
            <div className="route-status">
              <span>{lastIntent}</span>
              <span>{lastState}</span>
            </div>
          </div>

          <div className="message-list" aria-live="polite">
            {messages.map((message) => (
              <div className={`message-row ${message.role}`} key={message.id}>
                <div className="avatar">{message.role === "assistant" ? "CP" : "JD"}</div>
                <div className="message-body">
                  <div className="message-label">
                    {message.role === "assistant" ? "ClinicPilot" : "John Doe"}
                    {message.mode && <span className="inline-mode">{message.mode}</span>}
                  </div>
                  <div className="message-bubble">{message.text}</div>
                  <SourceChips sources={message.sources ?? []} />
                </div>
              </div>
            ))}
            {isSending && (
              <div className="message-row assistant">
                <div className="avatar">CP</div>
                <div className="typing" aria-label="Assistant is typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {messages.length === 1 && (
            <div className="prompt-row">
              {demoPrompts.map((prompt) => (
                <button type="button" key={prompt} onClick={() => setInput(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
          )}

          <form className="composer" onSubmit={submitMessage}>
            <label htmlFor="chat-input">Message ClinicPilot</label>
            <div className="composer-row">
              <textarea
                id="chat-input"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask a question or start booking an appointment…"
                rows={2}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <button className="button primary" type="submit" disabled={isSending || !input.trim()}>
                {isSending ? "Sending…" : "Send"}
              </button>
            </div>
          </form>
        </article>

        <aside className="panel bookings-panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">DATABASE VIEW</div>
              <h2>Patient bookings</h2>
            </div>
            <button
              className="button secondary compact"
              type="button"
              onClick={() => void refreshBookings()}
              disabled={isRefreshing}
            >
              {isRefreshing ? "Refreshing…" : "Refresh"}
            </button>
          </div>

          <div className="patient-card">
            <div className="patient-initials">JD</div>
            <div>
              <strong>John Doe</strong>
              <span>P001 · Demo patient</span>
            </div>
            <div className="allergy-tag">Allergies: Penicillin, Peanuts</div>
          </div>

          <div className="booking-list">
            {bookings.length === 0 && !isRefreshing && (
              <div className="empty-state">No booking records were returned.</div>
            )}
            {bookings.map((booking) => (
              <article className="booking-card" key={booking.booking_id}>
                <div className="booking-date">
                  <strong>{booking.booking_date}</strong>
                  <span>{formatTime(booking.booking_time)}</span>
                </div>
                <div className="booking-details">
                  <div className="booking-title-row">
                    <h3>{booking.treatment_name}</h3>
                    <span className={`status-badge ${booking.status.toLowerCase()}`}>
                      {booking.status}
                    </span>
                  </div>
                  <p>{booking.doctor_name}</p>
                  <div className="booking-meta">
                    <span>{booking.booking_id}</span>
                    <span>{booking.doctor_id} / {booking.treatment_id}</span>
                  </div>
                  {booking.notes && <div className="booking-note">{booking.notes}</div>}
                </div>
              </article>
            ))}
          </div>
          <p className="data-note">
            This panel is loaded from SQLite through <code>GET /api/bookings</code> after every
            assistant response.
          </p>
        </aside>
      </section>
    </main>
  );
}

