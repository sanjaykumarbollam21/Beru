/**
 * Desktop Personalization & Settings View Controller.
 * Manages user preferences, routines, remembered facts, and learning toggles.
 */

class PersonalizationViewController {
  constructor(hubBaseUrl, deviceToken) {
    this.hubBaseUrl = hubBaseUrl;
    this.deviceToken = deviceToken;
  }

  get headers() {
    return {
      'Authorization': `Bearer ${this.deviceToken}`,
      'Content-Type': 'application/json'
    };
  }

  async loadPersonalization() {
    const res = await fetch(`${this.hubBaseUrl}/personalization`, {
      method: 'GET',
      headers: this.headers
    });
    return res.json();
  }

  async setLearningEnabled(enabled) {
    return this.setPreference('learning_enabled', enabled);
  }

  async setPreference(key, value) {
    const res = await fetch(`${this.hubBaseUrl}/personalization/preferences/${key}`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify({ value })
    });
    return res.json();
  }

  async deletePreference(key) {
    const res = await fetch(`${this.hubBaseUrl}/personalization/preferences/${key}`, {
      method: 'DELETE',
      headers: this.headers
    });
    return res.json();
  }

  async deleteFact(factId) {
    const res = await fetch(`${this.hubBaseUrl}/personalization/facts/${factId}`, {
      method: 'DELETE',
      headers: this.headers
    });
    return res.json();
  }

  async deleteRoutine(name) {
    const res = await fetch(`${this.hubBaseUrl}/personalization/routines/${encodeURIComponent(name)}`, {
      method: 'DELETE',
      headers: this.headers
    });
    return res.json();
  }

  async exportData() {
    const res = await fetch(`${this.hubBaseUrl}/personalization/export`, {
      method: 'POST',
      headers: this.headers
    });
    return res.json();
  }

  async resetAll() {
    const res = await fetch(`${this.hubBaseUrl}/personalization`, {
      method: 'DELETE',
      headers: this.headers
    });
    return res.json();
  }
}

module.exports = { PersonalizationViewController };
