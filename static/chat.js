/**
 * Library Book Finder Bot - Client Controller
 */

document.addEventListener("DOMContentLoaded", () => {
    const SESSION_KEY = "library_bot_session_id";
    const HISTORY_KEY = "library_bot_history";

    const chatMessages = document.getElementById("chatMessages");
    const chatForm = document.getElementById("chatForm");
    const messageInput = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    const newChatBtn = document.getElementById("newChatBtn");

    let currentSessionId = "";

    /**
     * Initializes or retrieves the session ID from sessionStorage.
     */
    function initSession() {
        let storedSession = sessionStorage.getItem(SESSION_KEY);
        if (!storedSession) {
            storedSession = typeof crypto.randomUUID === "function"
                ? crypto.randomUUID()
                : "session_" + Math.random().toString(36).substring(2, 11) + Date.now().toString(36);
            sessionStorage.setItem(SESSION_KEY, storedSession);
        }
        currentSessionId = storedSession;
    }

    /**
     * Escapes raw HTML to prevent XSS injection.
     */
    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Formats bot replies safely:
     * - Escapes HTML
     * - Converts **text** to <strong>text</strong>
     * - Converts *text* to <em>text</em>
     * - Preserves newlines using <br>
     */
    function formatBotMessage(text) {
        let safe = escapeHtml(text);
        // Replace bold **text**
        safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        // Replace italic *text*
        safe = safe.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
        // Replace newlines
        safe = safe.replace(/\r?\n/g, "<br>");
        return safe;
    }

    /**
     * Scrolls chat to the latest message.
     */
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    /**
     * Appends a message bubble to the chat container.
     */
    function appendMessage(sender, text, isError = false) {
        const row = document.createElement("div");
        row.className = `message-row ${sender === "user" ? "user-row" : "bot-row"}`;

        const bubble = document.createElement("div");
        bubble.className = `message-bubble ${sender === "user" ? "user-bubble" : (isError ? "error-bubble" : "bot-bubble")}`;

        if (sender === "user") {
            bubble.textContent = text;
        } else {
            bubble.innerHTML = formatBotMessage(text);
        }

        row.appendChild(bubble);
        chatMessages.appendChild(row);
        scrollToBottom();

        return row;
    }

    /**
     * Saves chat history to sessionStorage.
     */
    function saveHistory(sender, text) {
        try {
            const raw = sessionStorage.getItem(HISTORY_KEY);
            const history = raw ? JSON.parse(raw) : [];
            history.push({ sender, text });
            sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        } catch (e) {
            console.warn("Could not save chat history to sessionStorage:", e);
        }
    }

    /**
     * Displays typing indicator dots.
     */
    function showTypingIndicator() {
        const row = document.createElement("div");
        row.id = "typingIndicator";
        row.className = "message-row bot-row";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble bot-bubble typing-bubble";
        bubble.innerHTML = `
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
        `;

        row.appendChild(bubble);
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    /**
     * Removes the typing indicator.
     */
    function removeTypingIndicator() {
        const indicator = document.getElementById("typingIndicator");
        if (indicator) {
            indicator.remove();
        }
    }

    /**
     * Renders the welcome message and quick-reply action buttons.
     */
    function renderWelcome() {
        const welcomeText = "Hi! I can help you find books, check availability and reserve them.";
        const welcomeRow = appendMessage("bot", welcomeText);

        // Add quick reply container directly under welcome bubble
        const quickReplies = document.createElement("div");
        quickReplies.className = "quick-replies-container";

        const options = [
            { label: "Find a book", starter: "Can you help me find a book?" },
            { label: "Check availability", starter: "Can you check the availability of a book?" },
            { label: "Reserve a book", starter: "I would like to reserve a book." }
        ];

        options.forEach(opt => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "quick-reply-btn";
            btn.textContent = opt.label;
            btn.addEventListener("click", () => {
                messageInput.value = opt.starter;
                handleSendMessage(opt.starter);
            });
            quickReplies.appendChild(btn);
        });

        welcomeRow.querySelector(".bot-bubble").appendChild(quickReplies);
        scrollToBottom();
    }

    /**
     * Restores conversation from sessionStorage or presents a fresh welcome message.
     */
    function loadConversation() {
        chatMessages.innerHTML = "";
        const rawHistory = sessionStorage.getItem(HISTORY_KEY);

        if (rawHistory) {
            try {
                const history = JSON.parse(rawHistory);
                if (Array.isArray(history) && history.length > 0) {
                    history.forEach(item => {
                        appendMessage(item.sender, item.text);
                    });
                    return;
                }
            } catch (err) {
                console.warn("Failed to parse stored chat history:", err);
            }
        }

        renderWelcome();
    }

    /**
     * Handles sending user message and calling the backend.
     */
    async function handleSendMessage(messageText) {
        const text = (messageText || messageInput.value).trim();
        if (!text) return;

        // Display user bubble and clear input
        appendMessage("user", text);
        saveHistory("user", text);
        messageInput.value = "";

        // Disable input & button while awaiting reply
        messageInput.disabled = true;
        sendBtn.disabled = true;
        showTypingIndicator();

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    session_id: currentSessionId,
                    message: text
                })
            });

            removeTypingIndicator();

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                const errMsg = errData.error || "Sorry, I couldn't reach the library server. Please try again.";
                appendMessage("bot", errMsg, true);
                saveHistory("bot", errMsg);
            } else {
                const data = await response.json();
                const reply = data.reply || "I didn't receive a response. Please try asking again.";
                appendMessage("bot", reply);
                saveHistory("bot", reply);
            }
        } catch (error) {
            removeTypingIndicator();
            const fallbackMsg = "Network error: Unable to contact the library bot. Please check your connection and try again.";
            appendMessage("bot", fallbackMsg, true);
            saveHistory("bot", fallbackMsg);
        } finally {
            messageInput.disabled = false;
            sendBtn.disabled = false;
            messageInput.focus();
            scrollToBottom();
        }
    }

    /**
     * Resets the conversation and establishes a fresh session.
     */
    function handleNewChat() {
        sessionStorage.removeItem(HISTORY_KEY);
        currentSessionId = typeof crypto.randomUUID === "function"
            ? crypto.randomUUID()
            : "session_" + Math.random().toString(36).substring(2, 11) + Date.now().toString(36);
        sessionStorage.setItem(SESSION_KEY, currentSessionId);

        chatMessages.innerHTML = "";
        renderWelcome();
        messageInput.value = "";
        messageInput.disabled = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }

    // Form submission (click Send or press Enter)
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleSendMessage();
    });

    // New Chat button
    newChatBtn.addEventListener("click", handleNewChat);

    // Initial setup
    initSession();
    loadConversation();
    messageInput.focus();
});
