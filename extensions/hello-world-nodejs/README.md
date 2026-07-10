# Node.js: Hello World

A minimal Node.js HTTP server that returns a JSON greeting. It's the smallest
example of publishing Node.js content to Posit Connect, and a starting point you
can build any Node.js service on.

## How it works

Connect runs Node.js content by starting your app and routing traffic to it.
Three things make that work, and they're the pattern to copy for any Node.js app:

- **`index.js`**: the entrypoint. It creates an HTTP server and listens on the
  port Connect assigns via the `PORT` environment variable (falling back to a
  local port for development). Connect auto-detects the entrypoint from
  `package.json`'s `main` field.
- **`package.json`**: declares `engines.node` (here `>=22.18.0`), which is
  required for Node.js content. At deploy time Connect reads this range and
  picks a matching Node.js version installed on the server.
- **`package-lock.json`**: pins dependencies so Connect installs the same
  versions it was tested with. (This app has no dependencies, so the lockfile
  is minimal, but it's still required.)

## Adapting it

Swap the request handler in `index.js` for your own routes, or replace the
built-in `http` server with a framework like Express. Just keep listening on
`process.env.PORT`. Add dependencies to `package.json` and run `npm install`
to update the lockfile.

## Usage

Once installed, the app responds to any request with:

```json
{ "message": "Hello from Node.js on Posit Connect!" }
```
