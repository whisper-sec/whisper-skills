---
description: Connect the WhisperGraph MCP connector, or diagnose why it is not answering
---

The user wants the WhisperGraph connector working. Work out which state they are in, then give them
only the steps for that state. Do not print the whole document.

**Do not run `claude mcp add` yourself.** Adding a server and completing a browser sign-in are the
user's actions on their own machine. Print the command; let them run it.

## Step 1: find out where they are

Call `explain_schema` with no arguments.

- **It returns a label catalogue** → they are already connected. Say so, name one thing they can now
  ask, and stop. Do not walk them through a setup they have already done.
- **The tool does not exist** → not connected. Go to step 2.
- **It returns 401, `unauthorized`, or `invalid token`** → added but not signed in. Go to step 3.
- **The tool exists and errors some other way** → go to step 4.

## Step 2: connect

Ask which client they are in if it is not obvious, then give them only that one.

**Claude Code**

```bash
claude mcp add --transport http whisper-graph https://mcp.whisper.security
```

Then `/mcp` inside the session, or `claude mcp login whisper-graph` from the shell, to finish the
browser sign-in. Options come before the server name; the URL is positional after it. Add
`--scope user` for every project, or `--scope project` to share the entry with the repository, but
only ever with OAuth. Never combine `--scope project` with a key: that scope writes a file meant to be
committed.

**Claude on the web, Desktop or mobile**

WhisperGraph is listed in the Claude Connectors Directory, so there is no URL to type. Customize →
Connectors → **+** → Browse connectors → **WhisperGraph** → **Connect**, then complete the sign-in. In a
chat, switch it on from the **+** button under Connectors. Anyone who added it earlier as a custom
connector by URL should remove that entry and connect from the directory instead.

On a Team or Enterprise organisation, an Owner enables the connector once for the organisation, and
each member then signs in from their own Customize → Connectors.

**Cursor, VS Code, Windsurf, ChatGPT, Codex, or another MCP client**

The per-client configuration is in the setup guide at
`https://www.whisper.security/docs/ai/mcp/setup`. All of them take the same URL over Streamable HTTP.
Fetch the guide with `read_docs`, passing the path `ai/mcp/setup`, if the tool is available; otherwise
send them the link.

Completing the sign-in needs a Whisper Security account. They can create one at
`https://console.whisper.security/sign-up`.

## Step 3: finish the sign-in

The connector is added but the OAuth flow never completed. This is the most common state, and it is
almost always the same cause: the browser tab opened, the user switched back to their work, and the
flow was abandoned.

Tell them to open their client's connector settings, find *WhisperGraph* (or *whisper-graph* if they
added it by URL), click **Connect**, and let the browser reach the page that says it is safe to close
the window. Then retry.

If their client cannot open a browser, such as a headless or CI environment, they can authenticate with
a static key instead, issued from the Whisper Security console. Put the key in an environment variable
and reference it, never inline, and never at project scope:

```bash
claude mcp add --transport http --scope user \
  --header "Authorization: Bearer \${WHISPER_API_KEY}" \
  whisper-graph https://mcp.whisper.security
```

The variable is expanded at connect time, so the configuration file holds the variable's name and never
the secret. Claude on the web and Claude Desktop do not accept custom headers in their connector
settings, so on those two use the directory and the OAuth sign-in. Never ask the user to paste a key
into the chat, never echo one back, and never write one into a file in their project.

## Step 4: is it them or is it us

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

Keep the `-A` flag. If the edge ever refuses a default agent string, the 403 looks exactly like an
outage.

## Step 5: confirm it works

Once `explain_schema` succeeds, prove it with something real rather than a schema dump:

> Investigate whisper.security: who runs it, where does it resolve, and what is around it?

Then tell them the four skills that are now live: `whisper-investigate` for a single indicator,
`whisper-bulk-triage` for a list, `whisper-cypher` when a question needs a custom query, and
`whisper-brand-protection` for impersonation and takedowns. They load on their own when a question
matches; there is nothing to invoke.

The connector also offers investigation prompts of its own, in clients that show MCP prompts. Those are
separate from these skills.
