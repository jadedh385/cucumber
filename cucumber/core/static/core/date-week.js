/* The week under the date field follows the day picked (U0.10a §7.5, AC10).

   The server works out every week: each <option> carries `data-week`, and
   this script only copies the picked one into the field's
   <output for="id_date">. No date maths here. Without the script the
   output shows the first option's week; what is saved is the date. */
(function () {
  "use strict";

  function showWeek(select) {
    const option = select.selectedOptions[0];
    const output = document.querySelector('output[for="' + CSS.escape(select.id) + '"]');
    if (option && option.dataset.week && output) {
      output.textContent = option.dataset.week;
    }
  }

  function showWeeksIn(root) {
    root.querySelectorAll("select[id]").forEach(showWeek);
  }

  document.addEventListener("change", function (event) {
    if (event.target instanceof HTMLSelectElement && event.target.id) {
      showWeek(event.target);
    }
  });
  // A page back from the cache, or a form htmx swapped in, keeps its pick.
  window.addEventListener("pageshow", function () {
    showWeeksIn(document);
  });
  document.addEventListener("htmx:load", function (event) {
    showWeeksIn(event.target);
  });
})();
