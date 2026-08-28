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
  var INPUT_TYPES = { text: "text", email: "email", tel: "tel" };
  var MAX_LENGTHS = { text: 120, email: 320, tel: 40, textarea: 2000 };

  var host = document.createElement("div");
  host.className = "embedlead-widget";
  host.setAttribute("data-embedlead-widget-id", widgetId);
  script.parentNode.insertBefore(host, script.nextSibling);

  function element(tag, text) {
    var node = document.createElement(tag);
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  function setStatus(text, isError) {
    var status = host.querySelector("[data-embedlead-status]");
    if (!status) {
      return;
    }
    status.textContent = text;
    status.setAttribute("data-state", isError ? "error" : "info");
  }

  function control(field) {
    var isArea = field.kind === "textarea";
    var node = document.createElement(isArea ? "textarea" : "input");
    if (!isArea) {
      node.type = INPUT_TYPES[field.kind] || "text";
    }
    node.name = field.name;
    node.maxLength = MAX_LENGTHS[field.kind] || MAX_LENGTHS.text;
    if (field.required) {
      node.required = true;
    }
    return node;
  }

  function honeypot() {
    var wrapper = document.createElement("div");
    wrapper.style.cssText = "position:absolute;left:-5000px;";
    wrapper.setAttribute("aria-hidden", "true");
    var label = element("label", "Website ");
    var input = document.createElement("input");
    input.name = "website";
    input.tabIndex = -1;
    input.autocomplete = "off";
    label.appendChild(input);
    wrapper.appendChild(label);
    return wrapper;
  }

  function render(payload) {
    var config = payload.config;
    var form = document.createElement("form");
    form.setAttribute("novalidate", "novalidate");
    form.setAttribute("data-theme", config.theme);

    form.appendChild(element("h3", config.title));
    if (config.description) {
      form.appendChild(element("p", config.description));
    }

    config.fields.forEach(function (field) {
      var label = element("label", field.label + " ");
      label.appendChild(control(field));
      form.appendChild(label);
    });

    form.appendChild(honeypot());
    var button = element("button", config.submit_label);
    button.type = "submit";
    form.appendChild(button);
    var status = element("p");
    status.setAttribute("data-embedlead-status", "");
    status.setAttribute("role", "status");
    form.appendChild(status);
    host.appendChild(form);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      button.disabled = true;
      setStatus("Sending...", false);

      var body = {};
      config.fields.forEach(function (field) {
        var value = form.elements[field.name].value;
        body[field.name] = value === "" ? null : value;
      });
      var trap = form.elements.website.value;
      if (trap) {
        body.website = trap;
      }

      fetch(base + "/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "omit",
        body: JSON.stringify(body),
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
          if (response.status === 413) {
            setStatus("That message is too large.", true);
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
