(() => {
  const nav = document.getElementById('siteNav');
  const card = document.getElementById('heroCard');
  const stage = document.getElementById('deviceStage');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const io = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) entry.target.classList.add('visible');
  }, { threshold: .12 });
  document.querySelectorAll('.reveal').forEach(el => io.observe(el));

  window.addEventListener('scroll', () => {
    nav?.classList.toggle('scrolled', window.scrollY > 12);
    if (!reduced && card && stage) {
      const rect = stage.getBoundingClientRect();
      const progress = Math.max(-1, Math.min(1, (window.innerHeight * .62 - rect.top) / window.innerHeight));
      card.style.transform = `rotateX(${4 - Math.max(0, progress) * 3.6}deg) translateY(${Math.min(0, progress) * 8}px)`;
    }
  }, { passive: true });
})();
