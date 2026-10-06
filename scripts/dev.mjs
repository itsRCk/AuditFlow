import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';

const python = existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python';
const children = [
  spawn(
    python,
    ['-m', 'uvicorn', 'server.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
    { stdio: 'inherit' },
  ),
  spawn('node_modules/.bin/vite', [], { stdio: 'inherit' }),
];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  children.forEach((child) => child.kill('SIGTERM'));
  setTimeout(() => process.exit(code), 500);
}
children.forEach((child) => {
  child.on('error', (error) => {
    console.error(error);
    stop(1);
  });
  child.on('exit', (code) => {
    if (!stopping) stop(code ?? 1);
  });
});
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
