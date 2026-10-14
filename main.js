/* MSE Press × The Dot: interactions */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- nav: scroll state, burger, active link ---------- */
  const nav = $('.nav');
  const burger = $('.burger');
  burger.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    burger.setAttribute('aria-expanded', open);
  });
  $$('.nav-links a').forEach(a => a.addEventListener('click', () => {
    nav.classList.remove('open');
    burger.setAttribute('aria-expanded', 'false');
  }));

  const progress = $('.scroll-progress');
  const onScroll = () => {
    const y = scrollY;
    nav.classList.toggle('scrolled', y > 40);
    const max = document.documentElement.scrollHeight - innerHeight;
    progress.style.width = (max > 0 ? (y / max) * 100 : 0) + '%';
  };
  addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  const links = $$('.nav-links a');
  const spy = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + e.target.id));
    });
  }, { rootMargin: '-45% 0px -50% 0px' });
  links.forEach(l => { const t = $(l.getAttribute('href')); if (t) spy.observe(t); });

  /* ---------- cursor glow ---------- */
  const glow = $('.cursor-glow');
  addEventListener('pointermove', e => {
    glow.style.left = e.clientX + 'px';
    glow.style.top = e.clientY + 'px';
  }, { passive: true });

  /* ---------- reveal on scroll + counters ---------- */
  const animateCount = el => {
    const to = +el.dataset.to;
    if (reduced) { el.textContent = to; return; }
    const dur = 1600, t0 = performance.now();
    const step = now => {
      const p = Math.min((now - t0) / dur, 1);
      el.textContent = Math.round(to * (1 - Math.pow(1 - p, 4)));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      const el = e.target;
      const siblings = $$('.reveal', el.parentElement);
      el.style.transitionDelay = Math.min(siblings.indexOf(el), 5) * 90 + 'ms';
      el.classList.add('in');
      $$('.count', el).forEach(animateCount);
      io.unobserve(el);
    });
  }, { threshold: .15 });
  $$('.reveal').forEach(el => io.observe(el));

  /* ---------- tilt cards ---------- */
  if (!reduced && matchMedia('(hover: hover)').matches) {
    $$('.tilt').forEach(card => {
      card.addEventListener('pointermove', e => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - .5;
        const y = (e.clientY - r.top) / r.height - .5;
        card.style.transform = `perspective(700px) rotateY(${x * 12}deg) rotateX(${-y * 12}deg) translateY(-4px)`;
      });
      card.addEventListener('pointerleave', () => { card.style.transform = ''; });
    });
  }

  /* ---------- hero network canvas (geo nodes) ---------- */
  const canvas = $('#net');
  const ctx = canvas.getContext('2d');
  let W, H, pts = [];
  const colors = ['#22d3ee', '#a3e635', '#ff3d81', '#7c5cff', '#ff9f1c'];
  const resize = () => {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.min(90, Math.floor((W * H) / 16000));
    pts = Array.from({ length: n }, () => ({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - .5) * .35, vy: (Math.random() - .5) * .35,
      r: Math.random() * 1.8 + .6, c: colors[Math.floor(Math.random() * colors.length)]
    }));
  };
  const mouse = { x: -999, y: -999 };
  canvas.parentElement.addEventListener('pointermove', e => {
    const r = canvas.getBoundingClientRect();
    mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top;
  });
  canvas.parentElement.addEventListener('pointerleave', () => { mouse.x = mouse.y = -999; });
  let heroVisible = true;
  new IntersectionObserver(([e]) => { heroVisible = e.isIntersecting; }).observe(canvas);
  const draw = () => {
    if (heroVisible) {
      ctx.clearRect(0, 0, W, H);
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > W) p.vx *= -1;
        if (p.y < 0 || p.y > H) p.vy *= -1;
        const dx = p.x - mouse.x, dy = p.y - mouse.y, d = Math.hypot(dx, dy);
        if (d < 120) { p.x += dx / d; p.y += dy / d; }
      }
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const a = pts[i], b = pts[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 130) {
            ctx.strokeStyle = `rgba(150,140,255,${(1 - d / 130) * .28})`;
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      for (const p of pts) {
        ctx.fillStyle = p.c;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      }
    }
    if (!reduced) requestAnimationFrame(draw);
  };
  resize(); draw();
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(resize, 150); });

  /* ---------- lens compare slider ---------- */
  const cmp = $('#compare');
  if (cmp) {
    let dragging = false;
    const set = clientX => {
      const r = cmp.getBoundingClientRect();
      const pct = Math.max(4, Math.min(96, ((clientX - r.left) / r.width) * 100));
      cmp.style.setProperty('--pos', pct + '%');
    };
    cmp.addEventListener('pointerdown', e => { dragging = true; cmp.setPointerCapture(e.pointerId); set(e.clientX); });
    cmp.addEventListener('pointermove', e => { if (dragging || e.pointerType === 'mouse') set(e.clientX); });
    cmp.addEventListener('pointerup', () => { dragging = false; });
    cmp.addEventListener('pointerleave', () => { if (!dragging) cmp.style.setProperty('--pos', '50%'); });
  }

  /* ---------- Episode 0 run of show ---------- */
  const segs = [
    ['Cold open & welcome', 'The host introduces the podcast, the Press Club, and the idea of looking at one topic through two lenses.', '#ff3d81'],
    ['Guest introductions', 'Each guest says who they are and what they work on, in one or two sentences.', '#ff9f1c'],
    ['Geospatial Informatics', 'What it is, in plain words: infrastructure, territory and earth observation, with one or two real examples, the curriculum and typical careers.', '#22d3ee'],
    ['Ecological Informatics', 'What it is, in plain words: ecosystems, biodiversity and environmental data, with one or two real examples, the curriculum and typical careers.', '#a3e635'],
    ['Where the two meet', 'Overlap in coursework and projects, with one example where both fields work on the same place or problem.', '#7c5cff'],
    ['Student voices', 'Why they chose their path, what surprised them, and advice for prospective students.', '#f472b6'],
    ['Teaser & close', 'A preview of 2 or 3 upcoming episodes, thanks, and a call to action.', '#fde047']
  ];
  const rosBtns = $$('.ros'), rosBars = $$('.ros-bar span'), rosDetail = $('.ros-detail');
  const pick = i => {
    rosBtns.forEach((b, k) => b.classList.toggle('active', k === i));
    rosBars.forEach((b, k) => b.classList.toggle('active', k === i));
    rosDetail.style.setProperty('--c', segs[i][2]);
    rosDetail.innerHTML = `<b>${segs[i][0]}</b>${segs[i][1]}`;
  };
  let rosI = 0, rosTimer;
  const auto = () => { clearInterval(rosTimer); rosTimer = setInterval(() => pick(rosI = (rosI + 1) % segs.length), 4200); };
  [...rosBtns, ...rosBars].forEach(el => el.addEventListener('click', () => { pick(rosI = +el.dataset.i); auto(); }));
  pick(0); if (!reduced) auto();

  /* ---------- episodes carousel ---------- */
  const eps = $('#episodes');
  const stepW = () => (eps.firstElementChild?.getBoundingClientRect().width || 300) + 18;
  $('.sn.prev').addEventListener('click', () => eps.scrollBy({ left: -stepW(), behavior: 'smooth' }));
  $('.sn.next').addEventListener('click', () => eps.scrollBy({ left: stepW(), behavior: 'smooth' }));

  /* ---------- mock video: show lower third when in view ---------- */
  const mock = $('.mock');
  new IntersectionObserver(([e]) => {
    if (e.isIntersecting) setTimeout(() => mock.classList.add('show'), 900);
    else mock.classList.remove('show');
  }, { threshold: .5 }).observe(mock);

  /* ---------- gallery lightbox ---------- */
  const lb = document.createElement('div');
  lb.className = 'lightbox';
  lb.innerHTML = '<img alt="">';
  document.body.appendChild(lb);
  lb.addEventListener('click', () => lb.classList.remove('open'));
  addEventListener('keydown', e => { if (e.key === 'Escape') lb.classList.remove('open'); });
  $$('.gallery .ph').forEach(f => f.addEventListener('click', () => {
    const img = $('img', f);
    if (!img) return;
    $('img', lb).src = img.src; $('img', lb).alt = img.alt;
    lb.classList.add('open');
  }));
})();
