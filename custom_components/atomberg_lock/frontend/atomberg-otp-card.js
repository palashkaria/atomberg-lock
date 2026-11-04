/** Atomberg OTP dashboard card. Access codes stay in memory, never card config. */
class AtombergOTPCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._count = 1;
    this._codes = null;
    this._busy = false;
    this._generation = 0;
    this._onVisibility = () => { if (document.hidden) this._clear(); };
    this.shadowRoot.addEventListener("click", (event) => {
      const action = event.target.closest("button")?.dataset.action;
      if (action === "clear") this._clear();
      if (action === "read" || action === "refill") this._run(action);
    });
    this.shadowRoot.addEventListener("input", (event) => {
      if (event.target.id === "count") this._count = Number(event.target.value);
    });
  }
  setConfig(config) {
    if (config.entity && !config.entity.startsWith("lock.")) throw new Error("Choose a lock entity.");
    this._config = { ...config };
    this._clear();
  }
  set hass(hass) {
    const authKey = `${hass.user?.id}:${hass.user?.is_admin}`;
    const changedUser = this._authKey !== authKey;
    this._authKey = authKey;
    this._hass = hass;
    if (changedUser) this._clear();
    if (!this.shadowRoot.querySelector("ha-card")) this._render();
    const name = this._hass.states[this._config?.entity]?.attributes.friendly_name;
    this.shadowRoot.querySelector(".lock-name").textContent = name || this._config?.entity || "Choose your lock in the card editor";
  }
  connectedCallback() {
    document.addEventListener("visibilitychange", this._onVisibility);
    this._render();
  }
  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    this._clear();
  }
  _clear() {
    clearTimeout(this._timer);
    this._generation++;
    this._codes = null;
    this._message = "";
    this._error = false;
    this._render();
  }
  async _run(action) {
    if (this._busy || !this._config?.entity || !this._hass?.user?.is_admin) return;
    if (action === "refill" && (!Number.isInteger(this._count) || this._count < 1 || this._count > 10)) {
      this._message = "Enter a whole number from 1 to 10.";
      this._error = true;
      this._render();
      return;
    }
    this._clear();
    const generation = this._generation;
    const hass = this._hass;
    this._busy = true;
    this._message = action === "read" ? "Reading OTPs…" : "Writing and verifying OTPs…";
    this._render();
    try {
      const entry = await hass.callWS({ type: "config/entity_registry/get", entity_id: this._config.entity });
      if (entry.platform !== "atomberg_lock" || !entry.config_entry_id) throw new Error("wrong_integration");
      const service_data = { config_entry_id: entry.config_entry_id };
      if (action === "refill") service_data.count = this._count;
      // A hidden or reconfigured card must not initiate a write after lookup.
      if (generation !== this._generation || !this.isConnected || document.hidden) return;
      const result = await hass.callWS({ type: "call_service", domain: "atomberg_lock",
        service: action === "read" ? "get_remote_otps" : "refill_otps", service_data, return_response: true });
      if (generation !== this._generation || !this.isConnected || document.hidden) return;
      const codes = result?.response?.otps;
      if (!Array.isArray(codes) || codes.some(item => !Number.isInteger(item.slot) || item.slot < 1 || (typeof item.code !== "string" || !/^\d{6}$/.test(item.code)))) throw new Error("invalid_response");
      this._codes = codes.map(({slot, code}) => ({slot, code}));
      this._message = action === "read" ? (codes.length ? `${codes.length} OTP${codes.length === 1 ? "" : "s"} in the pool` : "No OTPs in the pool") : `${codes.length} new OTP${codes.length === 1 ? "" : "s"} verified`;
      this._timer = setTimeout(() => this._clear(), 120000);
    } catch {
      if (generation !== this._generation) return;
      this._error = true;
      this._message = action === "refill" ? "Refill could not be verified. Read the pool before retrying; some codes may have been written." : "Could not read OTPs. Choose an Atomberg lock, close the phone app, and check Bluetooth range.";
    } finally {
      this._busy = false;
      this._render();
    }
  }
  _render() {
    if (!this.shadowRoot) return;
    const canUse = Boolean(this._config?.entity && this._hass?.user?.is_admin);
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;color:var(--primary-text-color,#212121);font-family:var(--paper-font-body1_-_font-family,system-ui)}
      ha-card{display:block;background:var(--ha-card-background,var(--card-background-color,#fff));border:1px solid var(--ha-card-border-color,var(--divider-color,#ddd));border-radius:var(--ha-card-border-radius,12px);overflow:hidden}
      .content{padding:20px}h2{font-size:20px;font-weight:500;margin:0 0 6px}.lock-name{margin:0 0 20px;color:var(--secondary-text-color,#606060);overflow-wrap:anywhere}
      .actions{display:flex;align-items:end;flex-wrap:wrap;gap:12px}label{display:flex;flex-direction:column;gap:6px;font-size:14px}
      input,button,select{font:inherit;box-sizing:border-box}input{width:72px;min-height:44px;padding:8px;background:var(--secondary-background-color,#f5f5f5);color:inherit;border:1px solid var(--divider-color,#888);border-radius:6px}
      button{min-height:44px;padding:10px 16px;background:transparent;color:var(--primary-color,#006d9c);border:1px solid currentColor;border-radius:var(--ha-card-border-radius,12px);cursor:pointer}
      button:hover:not(:disabled){background:var(--secondary-background-color,#eee)}button:disabled{opacity:.5;cursor:default}
      button:focus-visible,input:focus-visible{outline:3px solid var(--primary-color,#006d9c);outline-offset:3px}
      .message{font-size:14px;line-height:1.5;margin:20px 0 0}.error{color:var(--error-color,#b00020)}
      table{width:100%;border-collapse:collapse;margin-top:12px;text-align:left}th{font-size:13px;font-weight:500;color:var(--secondary-text-color,#606060)}th,td{padding:12px 4px;border-bottom:1px solid var(--divider-color,#ddd)}
      code{font-size:22px;letter-spacing:.12em;font-variant-numeric:tabular-nums;user-select:all}
      .footer{margin-top:16px;display:flex;align-items:center;justify-content:space-between;gap:12px}.note{font-size:13px;color:var(--secondary-text-color,#606060);line-height:1.5;margin:0}
      [hidden]{display:none!important}@media(max-width:360px){.content{padding:16px}.actions{gap:8px}button{padding:10px 12px}}
    </style><ha-card><div class="content"><h2>Door access</h2><p class="lock-name"></p>
    <div class="actions"><button data-action="read">Read OTPs</button><label>New codes<input id="count" type="number" min="1" max="10" step="1" inputmode="numeric"></label><button data-action="refill">Refill OTPs</button></div>
    <p class="message" role="status" aria-live="polite"></p><div class="results"></div>
    <div class="footer"><p class="note">Read again after using a code.<br>Codes clear after 2 minutes or when you leave.</p><button data-action="clear" hidden>Clear codes</button></div></div></ha-card>`;
    this.shadowRoot.querySelector(".lock-name").textContent = this._hass?.states[this._config?.entity]?.attributes.friendly_name || this._config?.entity || "Choose your lock in the card editor";
    const input = this.shadowRoot.querySelector("input"); input.value = this._count; input.disabled = this._busy || !canUse;
    for (const button of this.shadowRoot.querySelectorAll("button[data-action]")) button.disabled = this._busy || !canUse;
    const message = this.shadowRoot.querySelector(".message");
    message.textContent = !this._hass?.user?.is_admin ? "Sign in as an administrator to manage OTPs." : this._message || "Read existing codes or add new ones to the lock.";
    message.classList.toggle("error", Boolean(this._error));
    if (this._codes?.length) {
      const table = document.createElement("table"); table.innerHTML = "<thead><tr><th>Slot</th><th>OTP code</th></tr></thead>";
      const body = document.createElement("tbody");
      for (const item of this._codes) {
        const row = document.createElement("tr"); const slot = document.createElement("td");slot.textContent = item.slot;
        const cell = document.createElement("td"); const code = document.createElement("code");code.textContent = item.code;cell.append(code);row.append(slot,cell);body.append(row);
      }
      table.append(body);this.shadowRoot.querySelector(".results").append(table);
      this.shadowRoot.querySelector('[data-action="clear"]').hidden = false;
    }
  }
  getCardSize() { return this._codes?.length ? 4 + this._codes.length : 3; }
  static getConfigElement() { return document.createElement("atomberg-otp-card-editor"); }
  static getStubConfig(hass) { return { entity: Object.keys(hass.states).find(id => id.startsWith("lock.") && /atomberg/i.test(id + (hass.states[id].attributes.friendly_name || ""))) || "" }; }
}

class AtombergOTPCardEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});this.shadowRoot.addEventListener("change",event=>{this._config={...this._config,entity:event.target.value};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this._config},bubbles:true,composed:true}));});}
  setConfig(config){this._config={...config};this._render();}
  set hass(hass){this._hass=hass;this._render();}
  _render(){
    if(!this._hass || !this._config)return;
    this.shadowRoot.innerHTML='<style>label{display:flex;flex-direction:column;gap:8px}select{padding:12px;min-height:44px;font:inherit;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:6px}p{color:var(--secondary-text-color);font-size:14px}</style><label>Atomberg lock<select><option value="">Choose a lock</option></select></label><p>Select the lock belonging to the Atomberg integration. OTP controls require an administrator.</p>';
    const select=this.shadowRoot.querySelector("select");
    for(const [id,state] of Object.entries(this._hass.states).filter(([id])=>id.startsWith("lock."))){const option=document.createElement("option");option.value=id;option.textContent=state.attributes.friendly_name || id;select.append(option);}
    select.value=this._config.entity || "";
  }
}
function registerAtombergCard(){
  if(!customElements.get("atomberg-otp-card"))customElements.define("atomberg-otp-card",AtombergOTPCard);
  if(!customElements.get("atomberg-otp-card-editor"))customElements.define("atomberg-otp-card-editor",AtombergOTPCardEditor);
  window.customCards=window.customCards || [];
  if(!window.customCards.some(card=>card.type==="atomberg-otp-card"))window.customCards.push({type:"atomberg-otp-card",name:"Atomberg OTP",description:"Read and refill door codes directly from your dashboard.",preview:true});
}
// Wait for the native card and HA's registry setup before defining custom cards.
customElements.whenDefined("ha-card").then(registerAtombergCard);
