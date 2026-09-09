"""Small leaf constants shared across modules (no ydpy imports on purpose)."""

# Default browser-like UA for requests that do not impersonate a specific
# innertube client (clients define their own UA when they need one).
BROWSER_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)
