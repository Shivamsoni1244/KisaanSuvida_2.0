// location.js - Reusable cascading location selectors (State → District → Tehsil → Village)
// Works on both the registration and profile pages. No Select2 dependency.
// Reads saved ids from data-selected attributes (server-rendered) and restores them.
(function () {
  const API_BASE = '/api/location';

  const stateSelect = document.getElementById('state');
  const districtSelect = document.getElementById('district');
  const tehsilSelect = document.getElementById('tehsil');
  const villageSelect = document.getElementById('village');

  const selects = [stateSelect, districtSelect, tehsilSelect, villageSelect].filter(Boolean);
  if (selects.length === 0) return; // No location dropdowns on this page

  // Prevent duplicate initialisation if the script runs more than once.
  if (stateSelect && stateSelect.dataset.locationInit === '1') return;
  selects.forEach(s => { s.dataset.locationInit = '1'; });

  const LEVELS = [
    { select: stateSelect,     name: 'state',     placeholder: 'Select a state',     url: null,              child: districtSelect },
    { select: districtSelect,  name: 'district',  placeholder: 'Select a district',  url: '/api/location/districts/',   child: tehsilSelect },
    { select: tehsilSelect,    name: 'tehsil',    placeholder: 'Select a tehsil',    url: '/api/location/tehsils/',     child: villageSelect },
    { select: villageSelect,   name: 'village',   placeholder: 'Select a village',   url: '/api/location/villages/',    child: null },
  ];

  const indexOf = (sel) => LEVELS.findIndex(l => l.select === sel);

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  function option(text, value, selected) {
    const o = new Option(text, value, false, selected);
    return o;
  }

  function hasOption(select, value) {
    for (let i = 0; i < select.options.length; i++) {
      if (select.options[i].value === value) return true;
    }
    return false;
  }

  // Fill a <select>. `savedId` is applied only when explicitly passed (profile restore).
  function populate(select, items, placeholder, savedId) {
    select.innerHTML = '';
    const ph = option(placeholder, '', true);
    ph.disabled = true;
    select.appendChild(ph);
    (items || []).forEach(function (item) {
      select.add(option(item.name, item.id));
    });
    if (savedId && hasOption(select, savedId)) {
      select.value = savedId;
    }
    updateHiddenName(select);
  }

  function setPlaceholder(select, text) {
    select.innerHTML = '';
    const ph = option(text, '', true);
    ph.disabled = true;
    select.appendChild(ph);
    updateHiddenName(select);
  }

  function resetBelow(startIndex) {
    for (let i = startIndex + 1; i < LEVELS.length; i++) {
      const s = LEVELS[i].select;
      if (!s) continue;
      s.value = '';
      setPlaceholder(s, LEVELS[i].placeholder);
    }
  }

  function updateHiddenName(select) {
    if (!select) return;
    const hidden = document.getElementById(select.id + '_name');
    if (!hidden) return;
    const idx = select.selectedIndex;
    if (idx <= 0) { hidden.value = ''; return; }
    hidden.value = select.options[idx].text || '';
  }

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------
  function fetchJson(url) {
    return fetch(url, { credentials: 'same-origin' })
      .then(function (resp) {
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.json();
      });
  }

  function setLoading(select) {
    setPlaceholder(select, 'Loading…');
    select.disabled = true;
  }

  function setError(select, label) {
    setPlaceholder(select, 'Unable to load ' + label);
    select.disabled = false;
  }

  // Load children of `parentSelect` into `childSelect`.
  // savedId: id to pre-select (profile restore). null = normal user flow.
  // onSelected: called after child is populated and has a value (used to continue restore chain).
  function loadChildren(parentSelect, childLevel, savedId, onSelected) {
    const parentId = parentSelect.value;
    const child = childLevel.select;
    const ph = childLevel.placeholder;

    if (!parentId) {
      child.value = '';
      setPlaceholder(child, ph);
      return;
    }

    setLoading(child);
    // Reset anything below the child.
    var childIdx = indexOf(child);
    resetBelow(childIdx);

    fetchJson(childLevel.url + parentId)
      .then(function (data) {
        child.disabled = false;
        populate(child, data, ph, savedId);
        if (child.value && typeof onSelected === 'function') onSelected();
      })
      .catch(function () {
        setError(child, childLevel.name);
      });
  }

  // ------------------------------------------------------------------
  // Change handlers (user-driven)
  // ------------------------------------------------------------------
  function onStateChange() {
    updateHiddenName(stateSelect);
    resetBelow(0);
    if (stateSelect.value) loadChildren(stateSelect, LEVELS[1], null, null);
  }

  function onDistrictChange() {
    updateHiddenName(districtSelect);
    resetBelow(1);
    if (districtSelect.value) loadChildren(districtSelect, LEVELS[2], null, null);
  }

  function onTehsilChange() {
    updateHiddenName(tehsilSelect);
    resetBelow(2);
    if (tehsilSelect.value) loadChildren(tehsilSelect, LEVELS[3], null, null);
  }

  function onVillageChange() {
    updateHiddenName(villageSelect);
  }

  // ------------------------------------------------------------------
  // Initialisation & profile restore
  // ------------------------------------------------------------------
  function init() {
    // Wire change listeners once.
    if (stateSelect)     stateSelect.addEventListener('change', onStateChange);
    if (districtSelect)  districtSelect.addEventListener('change', onDistrictChange);
    if (tehsilSelect)    tehsilSelect.addEventListener('change', onTehsilChange);
    if (villageSelect)   villageSelect.addEventListener('change', onVillageChange);

    // Load top-level states, then restore saved selections down the chain.
    fetchJson(API_BASE + '/states')
      .then(function (data) {
        if (!stateSelect) return;
        populate(stateSelect, data, LEVELS[0].placeholder, stateSelect.dataset.selected || null);
        if (stateSelect.value) restoreChain(0);
      })
      .catch(function () {
        if (stateSelect) setError(stateSelect, LEVELS[0].name);
      });
  }

  function restoreChain(level) {
    // level 0 = state (already loaded), then load districts/tehsils/village using saved ids.
    if (level >= LEVELS.length - 1) return;
    var current = LEVELS[level];
    var next = LEVELS[level + 1];
    if (!current.select || !next.select) return;
    if (!current.select.value) return;
    loadChildren(current.select, next, next.select.dataset.selected || null, function () {
      restoreChain(level + 1);
    });
  }

  document.addEventListener('DOMContentLoaded', init);

  // Expose for registration form validation.
  window.LocationCascade = {
    isValid: function () {
      return selects.every(function (s) { return s && s.value !== ''; });
    },
    values: function () {
      var out = {};
      selects.forEach(function (s) { out[s.id] = s.value; });
      return out;
    }
  };
})();
