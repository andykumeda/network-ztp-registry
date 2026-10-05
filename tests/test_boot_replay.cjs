const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const elements = {};
const timers = new Map();
let timerId = 0;
const context = {
  document: {getElementById: key => elements[key] ??= {
    textContent: '', hidden: true, disabled: false, scrollHeight: 0, focus() {},
  }},
  setTimeout: fn => {timers.set(++timerId, fn); return timerId;},
  clearTimeout: id => timers.delete(id),
};
vm.createContext(context);
vm.runInContext(script.slice(script.indexOf('  const bootDemoLines'),
                            script.indexOf('  // ── Init')), context);
context.startBootDemo();
assert.equal(elements['boot-demo'].hidden, false);
context.toggleBootDemo();
assert.equal(timers.size, 0);
assert.equal(elements['boot-status'].textContent, 'Paused');
context.toggleBootDemo();
while (timers.size) {
  const [id, fn] = timers.entries().next().value;
  timers.delete(id);
  fn();
}
assert.equal(elements['boot-status'].textContent, 'Complete');
assert.equal(elements['boot-pause'].disabled, true);
assert.equal(elements['boot-output'].textContent.trim().split('\n').length, 19);
context.startBootDemo();
assert.equal(timers.size, 1);
context.startBootDemo();
assert.equal(timers.size, 1);
context.closeBootDemo();
assert.equal(timers.size, 0);
assert.equal(elements['boot-demo'].hidden, true);
console.log('Replay syntax, completion, pause/resume, restart cancellation and close passed.');
