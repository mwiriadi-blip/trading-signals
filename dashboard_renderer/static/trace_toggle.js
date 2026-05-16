
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('details[data-instrument]').forEach(function(el) {
    el.addEventListener('toggle', function() {
      var openKeys = Array.from(
        document.querySelectorAll('details[data-instrument][open]')
      ).map(function(d) { return d.getAttribute('data-instrument'); }).join(',');
      document.cookie = 'tsi_trace_open=' + openKeys
        + '; Path=/; SameSite=Lax; Max-Age=31536000; Secure';
    });
  });
  document.querySelectorAll('.trace-indicator-name').forEach(function(cell) {
    cell.addEventListener('click', function() {
      var isOpen = this.getAttribute('data-formula-open') === 'true';
      var next = this.closest('tr').nextElementSibling;
      if (next && next.classList.contains('formula-row')) {
        next.hidden = isOpen;
        this.setAttribute('data-formula-open', isOpen ? 'false' : 'true');
      }
    });
  });
});
