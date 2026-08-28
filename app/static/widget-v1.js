(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) {
    return;
  }
  var widgetId = script.getAttribute("data-widget-id");
  if (!widgetId) {
    return;
  }

  var origin = new URL(script.src).origin;
  var base = origin + "/api/v1/public/widgets/" + encodeURIComponent(widgetId);

  var host = document.createElement("div");
  host.className = "embedlead-widget";
  host.setAttribute("data-embedlead-widget-id", widgetId);
  script.parentNode.insertBefore(host, script.nextSibling);

  function setStatus(text, isError) {
    var status = host.querySelector("[data-embedlead-status]");
    if (!status) {
      return;
    }
    status.textContent = text;
    status.setAttribute("data-state", isError ? "error" : "info");
  }

  function render(config) {
    var form = document.createElement("form");
    form.setAttribute("novalidate", "novalidate");
    form.innerHTML = [
      '<h3 data-embedlead-title></h3>',
      '<label>Name <input name="name" required maxlength="120" /></label>',
      '<label>Email <input name="email" type="email" required maxlength="320" /></label>',
      '<label>Message <textarea name="message" maxlength="2000"></textarea></label>',
      '<div style="position:absolute;left:-5000px;" aria-hidden="true">',
      '<label>Website <input name="website" tabindex="-1" autocomplete="off" /></label>',
      "</div>",
      '<button type="submit">Send</button>',
      '<p data-embedlead-status role="status"></p>',
    ].join("");
    form.querySelector("[data-embedlead-title]").textContent = config.name;
    host.appendChild(form);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button");
      button.disabled = true;
      setStatus("Sending...", false);

      var payload = {
        name: form.elements.name.value,
        email: form.elements.email.value,
        message: form.elements.message.value || null,
      };
      var honeypot = form.elements.website.value;
      if (honeypot) {
        payload.website = honeypot;
      }

      fetch(base + "/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "omit",
        body: JSON.stringify(payload),
      })
        .then(function (response) {
          if (response.status === 202) {
            form.reset();
            setStatus("Thank you. We received your message.", false);
            return;
          }
          if (response.status === 429) {
            setStatus("Too many attempts. Please try again shortly.", true);
            return;
          }
          if (response.status === 422) {
            setStatus("Please check the details and try again.", true);
            return;
          }
          setStatus("Sorry, something went wrong.", true);
        })
        .catch(function () {
          setStatus("Network problem. Please try again.", true);
        })
        .then(function () {
          button.disabled = false;
        });
    });
  }

  fetch(base + "/config", { credentials: "omit" })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("config unavailable");
      }
      return response.json();
    })
    .then(render)
    .catch(function () {
      host.textContent = "";
    });
})();
