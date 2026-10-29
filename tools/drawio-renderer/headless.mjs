// Isolated MCP subprocess only: the official tool opens a browser as a side
// effect. Block subprocess launches, but keep its MCP/XML processing unchanged.
// Never load this shim in the application or the Desktop exporter process.
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { EventEmitter } from 'node:events';
childProcess.spawn = () => {
  const child = new EventEmitter();
  child.unref = () => child;
  child.kill = () => true;
  queueMicrotask(() => child.emit('close', 0));
  return child;
};
syncBuiltinESMExports();
