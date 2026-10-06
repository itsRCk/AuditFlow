// Apply the saved or system theme before the app and stylesheet paint.
(function () {
  var theme;
  try {
    theme = localStorage.getItem('auditflow.theme');
  } catch (_) {}
  if (theme !== 'light' && theme !== 'dark') {
    theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.style.colorScheme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    .setAttribute('content', theme === 'dark' ? '#000000' : '#ffffff');
})();
