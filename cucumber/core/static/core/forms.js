/* One tap, one request (U0.10a §4.2, AC12).

   A plain form is marked as sending on its first submit, and every later
   submit of it is cancelled. Its button shows it is busy (aria-disabled and
   `is-sending`) but is never `disabled`: a disabled button drops its
   name=value from the request. A page back from the browser's back-forward
   cache works again. HTMX forms are left to htmx (`hx-sync`,
   `hx-disabled-elt`, written by the kit's form template). */
(function () {
  "use strict";

  const HTMX_FORM = "[hx-post], [hx-put], [hx-patch], [hx-delete], " +
    "[data-hx-post], [data-hx-put], [data-hx-patch], [data-hx-delete]";
  const SUBMIT_BUTTON = "button:not([type]), button[type=submit], input[type=submit]";

  function markSending(form, button) {
    form.setAttribute("data-sending", "");
    if (button) {
      button.setAttribute("aria-disabled", "true");
      button.classList.add("is-sending");
    }
  }

  function markReady(form) {
    form.removeAttribute("data-sending");
    form.querySelectorAll(".is-sending").forEach(function (button) {
      button.removeAttribute("aria-disabled");
      button.classList.remove("is-sending");
    });
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.matches(HTMX_FORM)) {
      return;
    }
    if (form.hasAttribute("data-sending")) {
      event.preventDefault();
      return;
    }
    if (!event.defaultPrevented) {
      markSending(form, event.submitter || form.querySelector(SUBMIT_BUTTON));
    }
  });

  window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
      document.querySelectorAll("form[data-sending]").forEach(markReady);
    }
  });
})();
