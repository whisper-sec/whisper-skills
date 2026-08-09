---
description: Connect the WhisperGraph MCP connector, or diagnose why it is not answering
---

The user wants the WhisperGraph connector working. Work out which state they are in, then give them
only the steps for that state — do not print the whole document.

**Do not run `claude mcp add` yourself.** Adding a server and completing a browser sign-in are the
user's actions on their own machine. Print the command; let them run it.

## Step 1 — find out where they are

Call `explain_schema` with no arguments.

- **It returns a label catalogue** → they are already connected. Say so, name one thing they can now
  ask, and stop. Do not walk them through a setup they have already done.
- **The tool does not exist** → not connected. Go to step 2.
- **It returns 401, `unauthorized`, or `invalid token`** → added but not signed in. Go to step 3.
- **The tool exists and errors some other way** → go to step 4.

## Step 2 — connect

Ask which client they are in if it is not obvious, then give them only that one.

**Claude Code**

```bash
claude mcp add --transport http whisper-graph https://mcp.whisper.security
```

Then `/mcp` inside the session, or `claude mcp login whisper-graph` from the shell, to finish the
browser sign-in. Options come before the server name; the URL is positional after it. Add
`--scope user` for every project, or `--scope project` to share the entry with the repository — but
only ever with OAuth. Never combine `--scope project` with a key: that scope writes a file meant to be
committed.

**Claude Desktop or Claude.ai**

Settings → Connectors → Add custom connector → `https://mcp.whisper.security` → Add. Then click
**Connect** next to *whisper-graph* and complete the sign-in. Adding it does not authenticate — the
Connect button is what starts the flow. On Claude.ai, also enable it in the chat via the **+** button.

**Cursor, VS Code, Windsurf, Codex, or another MCP client**

The per-client configuration is in the setup guide at
`https://www.whisper.security/docs/ai/mcp/setup`. All of them take the same URL over Streamable HTTP.
Fetch the page with `read_docs` if it is available, or send them the link.

They will need a Whisper Security account to complete the sign-in — `https://console.whisper.security/sign-up`.

## Step 3 — finish the sign-in

The connector is added but the OAuth flow never completed. This is the most common state, and it is
almost always the same cause: the browser tab opened, the user switched back to their work, and the
flow was abandoned.

Tell them to open their client's connector settings, find *whisper-graph*, click **Connect**, and let
the browser reach the page that says it is safe to close the window. Then retry.

If their client cannot open a browser — a headless or CI environment — they can authenticate with a
static key instead, issued from the Whisper Security console. Put the key in an environment variable and
reference it, never inline, and never at project scope:

```bash
claude mcp add --transport http --scope user \
  --header "Authorization: Bearer \${WHISPER_API_KEY}" \
  whisper-graph https://mcp.whisper.security
```

The variable is expanded at connect time, so the configuration file holds the variable's name and never
the secret. Claude.ai and Claude Desktop's connector UI do not accept custom headers; those two need the
OAuth flow or a local bridge. Never ask the user to paste a key into the chat, never echo one back, and
never write one into a file in their project.

## Step 4 — is it them or is it us

The public graph API answers with no key and no account, so it separates a client problem from a service
problem in one call. Run it:

```bash
curl -sS -A "whisper-setup-check/1.0" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.quota() YIELD key, value RETURN key, value"}' \
  https://graph.whisper.security/api/query
```

- **JSON back** → the service is up; the problem is the MCP connection. Go back to step 2 or 3.
- **An HTTP error** → the service, or the network between them and it. Report the status code.

The `-A` flag is not decoration: the edge rejects some default programmatic agent strings with a 403
that looks exactly like an outage.

## Step 5 — confirm it works

Once `explain_schema` succeeds, prove it with something real rather than a schema dump:

> Investigate whisper.security — who runs it, where does it resolve, and what is around it?

Then tell them the four skills that are now live: `whisper-investigate` for a single indicator,
`whisper-bulk-triage` for a list, `whisper-cypher` when a question needs a custom query, and
`whisper-brand-protection` for impersonation and takedowns. They load on their own when a question
matches; there is nothing to invoke.

The connector also registers slash-style investigation prompts of its own, one per gallery workflow.
Those are separate from these skills and are listed in the client's prompt menu.
