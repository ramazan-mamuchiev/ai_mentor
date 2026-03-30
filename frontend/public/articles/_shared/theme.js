/* Lexiro article theme sync.
   Reads ?theme= from URL and listens to postMessage from parent for live theme changes. */
(function () {
  function applyTheme(theme) {
    if (theme === 'dark' || theme === 'light') {
      document.documentElement.setAttribute('data-theme', theme);
    }
  }

  var params = new URLSearchParams(window.location.search);
  var initial = params.get('theme');
  if (initial) {
    applyTheme(initial);
  }

  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'lexiro-theme' && e.data.theme) {
      applyTheme(e.data.theme);
    }
  });
})();
