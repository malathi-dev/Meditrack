console.log("MediTrack Alerts Loaded");
setTimeout(function() {
  let alerts = document.querySelectorAll(".alert");
  alerts.forEach(alert => {
    alert.style.transition = "0.5s";
    alert.style.opacity = "0";
    setTimeout(() => alert.remove(), 500);
  });
}, 4000);
