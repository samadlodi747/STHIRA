(function () {
  import("/static/js/app.js?v=1").catch(function (error) {
    console.error("[steel-beam] could not load modular FastAPI adapter", error);
  });
})();
