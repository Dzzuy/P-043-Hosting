import test from 'node:test';
import assert from 'node:assert/strict';
import { copilotReason } from '../src/lib/copilotStatus.js';

test('renders public reasons without exposing unknown internal state', () => {
  assert.match(copilotReason('policy_conflict'), /chưa thống nhất/);
  assert.match(copilotReason('budget_exhausted'), /giới hạn/);
  assert.equal(copilotReason('internal_trace'), '');
  assert.equal(copilotReason(null), '');
});
