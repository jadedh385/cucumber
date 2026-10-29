/* When an HTMX request goes wrong, say how (U0.10a §4.3, AC13, AC14).

   The words are the page's, so they are translated: each is a
   <template id="trouble-NAME"> in the base page, and this script copies one
   into the banner `#request-trouble` (role="alert"). A timeout never says
   "not saved": the save may have reached the server. htmx re-enables Save
   when the request ends, however it ends. */
(function () {
  "use strict";

  const BANNER = "request-trouble";
  const TROUBLE_HEADER = "Cucumber-Trouble";

  function show(name) {
    const banner = document.getElementById(BANNER);
    const words = document.getElementById("trouble-" + name);
    if (banner && words) {
      banner.replaceChildren(words.content.cloneNode(true));
    }
  }

  function clear() {
    const banner = document.getElementById(BANNER);
    if (banner) {
      banner.replaceChildren();
    }
  }

  function troubleFor(answer) {
    if (answer.status === 503) {
      return "busy";
    }
    if (answer.status === 403) {
      const isStale = answer.getResponseHeader(TROUBLE_HEADER) === "stale-page";
      return isStale ? "stale-page" : "no-access";
    }
    return "server-error";
  }

  document.addEventListener("htmx:beforeRequest", clear);
  document.addEventListener("htmx:timeout", function () {
    show("not-confirmed");
  });
  document.addEventListener("htmx:sendError", function () {
    show("offline");
  });
  document.addEventListener("htmx:responseError", function (event) {
    show(troubleFor(event.detail.xhr));
  });
})();
