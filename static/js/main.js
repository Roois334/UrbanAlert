/* Urban Alert — JS principal */

// Navbar scroll effect
const navbar = document.getElementById('mainNav');
if (navbar) {
  window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 30);
  });
}

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    document.querySelectorAll('.alert-ua').forEach(el => {
      el.style.transition = 'opacity .4s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 400);
    });
  }, 4500);

  // Animate stats on scroll
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('fade-up');
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.stat-card, .card-ua').forEach(el => observer.observe(el));
});
