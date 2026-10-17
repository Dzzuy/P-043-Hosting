import { request } from "./client";

export const managerApi = {
  createAdvisor({ username, displayName, password }) {
    return request('/auth/advisors', {
      method: 'POST',
      body: JSON.stringify({ username, display_name: displayName, password }),
    });
  },

  getReviewQueue() {
    return request("/manager/reviews");
  },

  getAttempts({ advisorId = '', scenarioId = '', limit = 20, offset = 0 } = {}) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (advisorId.trim()) params.set('advisor_id', advisorId.trim());
    if (scenarioId.trim()) params.set('scenario_id', scenarioId.trim());
    return request(`/manager/attempts?${params}`);
  },

  getReviewDetail(sessionId) {
    return request(`/manager/reviews/${encodeURIComponent(sessionId)}`);
  },

  getVoiceUsage(sessionId) {
    return request(`/manager/reviews/${encodeURIComponent(sessionId)}/voice/usage`);
  },

  approveReview(sessionId, decision) {
    return request(`/manager/reviews/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      body: JSON.stringify(decision),
    });
  },

  getTeamOverview() {
    return request("/manager/overview");
  },

  getManagerHistory({ advisorId, scenarioId, limit = 50, offset = 0 } = {}) {
    const params = new URLSearchParams();
    if (advisorId) params.set("advisor_id", advisorId);
    if (scenarioId) params.set("scenario_id", scenarioId);
    if (limit) params.set("limit", String(limit));
    if (offset) params.set("offset", String(offset));
    const qs = params.toString();
    return request(`/manager/attempts${qs ? "?" + qs : ""}`);
  },

  getAdvisors() {
    return request('/manager/advisors');
  },

  getAssignments() {
    return request('/manager/assignments');
  },

  createAssignment(payload) {
    return request('/manager/assignments', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
