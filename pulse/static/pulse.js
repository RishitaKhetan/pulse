(function () {
  'use strict';

  var FLUSH_INTERVAL = 3000;
  var BATCH_SIZE = 10;

  var _endpoint = 'http://localhost:4747';
  var _userId = null;
  var _sessionId = null;
  var _queue = [];
  var _timer = null;

  function _uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  function _getSessionId() {
    if (_sessionId) return _sessionId;
    try {
      _sessionId = sessionStorage.getItem('_pulse_sid');
      if (!_sessionId) {
        _sessionId = _uuid();
        sessionStorage.setItem('_pulse_sid', _sessionId);
      }
    } catch (_) {
      _sessionId = _uuid();
    }
    return _sessionId;
  }

  function _send(events) {
    var url = _endpoint + '/events/batch';
    var body = JSON.stringify(events);
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: 'application/json' });
        navigator.sendBeacon(url, blob);
      } else {
        fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body,
          keepalive: true,
        }).catch(function () {});
      }
    } catch (_) {}
  }

  function _flush() {
    if (!_queue.length) return;
    var events = _queue.splice(0);
    _send(events);
  }

  function _scheduleFlush() {
    if (_timer) return;
    _timer = setTimeout(function () {
      _timer = null;
      _flush();
    }, FLUSH_INTERVAL);
  }

  function track(eventName, properties) {
    if (!eventName) return;
    var event = {
      event_name: eventName,
      user_id: _userId || null,
      session_id: _getSessionId(),
      properties: Object.assign(
        { url: window.location.href, referrer: document.referrer || null },
        properties || {}
      ),
    };
    _queue.push(event);
    if (_queue.length >= BATCH_SIZE) {
      clearTimeout(_timer);
      _timer = null;
      _flush();
    } else {
      _scheduleFlush();
    }
  }

  function identify(userId) {
    _userId = userId;
  }

  function _autoTrack() {
    track('page_view', { page: window.location.pathname });

    // SPA navigation via history.pushState
    var _orig = history.pushState.bind(history);
    history.pushState = function () {
      _orig.apply(history, arguments);
      track('page_view', { page: window.location.pathname });
    };
    window.addEventListener('popstate', function () {
      track('page_view', { page: window.location.pathname });
    });
    window.addEventListener('hashchange', function () {
      track('page_view', { page: window.location.pathname + window.location.hash });
    });
  }

  function init(config) {
    config = config || {};
    if (config.endpoint) _endpoint = config.endpoint.replace(/\/$/, '');
    if (config.userId) _userId = config.userId;

    if (config.autoTrack !== false) _autoTrack();

    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') _flush();
    });
    window.addEventListener('beforeunload', _flush);
  }

  window.Pulse = { init: init, track: track, identify: identify, flush: _flush };
})();
