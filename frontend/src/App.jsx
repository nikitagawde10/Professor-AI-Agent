import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8787";

export default function App() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    setAnswer("");

    try {
      const resp = await fetch(`${API_BASE}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: query }),
      });
      const data = await resp.json();
      if (!resp.ok)
        throw new Error(data?.detail || data?.error || "Request failed");
      setAnswer(data.answer || "");
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">
      <header>
        <h1>Spanish Professor</h1>
        <p className="subtitle">
          Beginner Spanish explained in English. Ask about words, grammar, or
          pronunciation. <br />
          Examples: <em>What does "guapo" mean?</em> ·{" "}
          <em>What comes after "nosotros"?</em> · <em>How to pronounce Ñ?</em>
        </p>
      </header>

      <form className="search" onSubmit={onSubmit}>
        <input
          type="text"
          placeholder='Try: What does "guapo" mean?'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Ask a Spanish question"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Thinking…" : "Ask"}
        </button>
      </form>

      {error && <div className="error">⚠️ {error}</div>}

      <section className="answer">
        {loading && <div className="skeleton" />}
        {!loading && answer && (
          <>
            <h2>Answer</h2>
            <div className="card markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {answer}
              </ReactMarkdown>
            </div>
          </>
        )}
      </section>

      <footer>
        <small>Powered by Ollama · mistral (local)</small>
      </footer>
    </div>
  );
}
