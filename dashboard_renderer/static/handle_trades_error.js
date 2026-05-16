
function handleTradesError(evt) {
  if (evt.detail.successful) return;
  var section = evt.target.closest('section');
  if (!section) return;
  var errorBox = section.querySelector('.error');
  if (!errorBox) return;
  var status = evt.detail.xhr.status;
  if (status === 401) {
    errorBox.innerHTML = '<p class="error-heading">Auth header missing or wrong — refresh the page</p>';
  } else if (status === 400) {
    var body;
    try { body = JSON.parse(evt.detail.xhr.responseText); } catch (e) {
      errorBox.innerHTML = '<p class="error-heading">Server error — see journald</p>';
      errorBox.hidden = false;
      return;
    }
    var heading = '<p class="error-heading">Could not save trade:</p>';
    var rows = (body.errors || []).map(function (e) {
      return '<div class="error-row"><code>' + e.field + '</code>: ' + e.reason + '</div>';
    }).join('');
    errorBox.innerHTML = heading + '<div class="error-rows">' + rows + '</div>';
  } else if (status === 409) {
    errorBox.innerHTML = '<p class="error-heading">' + evt.detail.xhr.responseText + '</p>';
  } else {
    errorBox.innerHTML = '<p class="error-heading">Server error — see journald: journalctl -u trading-signals-web</p>';
  }
  errorBox.hidden = false;
}
