(() => {
  'use strict';
  const header = document.querySelector('.site-header');
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#mobile-nav');
  const booking = document.querySelector('#booking-dialog');
  const lightbox = document.querySelector('#lightbox');
  let opener = null;
  const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 40);
  onScroll(); window.addEventListener('scroll', onScroll, { passive: true });
  function closeMenu() { nav.hidden = true; menu.setAttribute('aria-expanded', 'false'); menu.setAttribute('aria-label', '打开导航'); header.classList.remove('menu-open'); }
  menu.addEventListener('click', () => {
    const opening = nav.hidden; nav.hidden = !opening;
    menu.setAttribute('aria-expanded', String(opening)); menu.setAttribute('aria-label', opening ? '关闭导航' : '打开导航'); header.classList.toggle('menu-open', opening);
  });
  nav.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
  window.addEventListener('resize', () => { if (window.innerWidth > 760) closeMenu(); });
  function openDialog(dialog, trigger) { opener = trigger; closeMenu(); document.body.classList.add('modal-open'); dialog.showModal(); }
  document.querySelectorAll('[data-book]').forEach(button => button.addEventListener('click', () => {
    const room = button.dataset.room;
    document.querySelector('#booking-context').textContent = room ? `你正在咨询：${room}。与我们聊聊你的到访计划。` : '与我们聊聊你的到访计划。';
    document.querySelector('.copy-status').textContent = '';
    openDialog(booking, button);
  }));
  [booking, lightbox].forEach(dialog => {
    dialog.querySelector('[data-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => { if(event.target !== dialog) return; const r=dialog.getBoundingClientRect(); if(event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) dialog.close(); });
    dialog.addEventListener('close', () => { document.body.classList.remove('modal-open'); if (opener) opener.focus({preventScroll:true}); });
  });
  document.querySelector('[data-copy]').addEventListener('click', async event => {
    const status = document.querySelector('.copy-status');
    try { await navigator.clipboard.writeText(event.currentTarget.dataset.copy); status.textContent = '微信号已复制，可打开微信搜索添加。'; }
    catch { status.textContent = '请长按或选中上方微信号复制。'; }
  });
  let pictures = [], pictureIndex = 0;
  const galleryImage = lightbox.querySelector('img');
  const previous = lightbox.querySelector('.gallery-prev'), next = lightbox.querySelector('.gallery-next');
  function displayPicture(index) {
    pictureIndex = (index + pictures.length) % pictures.length;
    const picture = pictures[pictureIndex]; galleryImage.src = picture.src; galleryImage.alt = picture.alt;
    lightbox.querySelector('figcaption').textContent = picture.alt;
    lightbox.querySelector('.gallery-count').textContent = `${String(pictureIndex+1).padStart(2,'0')} / ${String(pictures.length).padStart(2,'0')}`;
    previous.hidden = next.hidden = pictures.length < 2;
  }
  document.querySelectorAll('[data-gallery]').forEach(button => button.addEventListener('click', () => {
    const group = [...document.querySelectorAll('[data-gallery]')].filter(item => item.dataset.gallery === button.dataset.gallery);
    pictures = group.map(item => {const img=item.querySelector('img');return {src:img.currentSrc||img.src,alt:img.alt};});
    displayPicture(group.indexOf(button)); openDialog(lightbox,button);
  }));
  previous.addEventListener('click', () => displayPicture(pictureIndex-1)); next.addEventListener('click', () => displayPicture(pictureIndex+1));
  lightbox.addEventListener('keydown', event => { if(event.key==='ArrowLeft'){event.preventDefault();displayPicture(pictureIndex-1);} if(event.key==='ArrowRight'){event.preventDefault();displayPicture(pictureIndex+1);} });
  let startX=0,startY=0;
  galleryImage.addEventListener('touchstart', event => {startX=event.changedTouches[0].clientX;startY=event.changedTouches[0].clientY;},{passive:true});
  galleryImage.addEventListener('touchend', event => {const dx=event.changedTouches[0].clientX-startX,dy=event.changedTouches[0].clientY-startY;if(Math.abs(dx)>50&&Math.abs(dx)>Math.abs(dy))displayPicture(pictureIndex+(dx<0?1:-1));},{passive:true});
})();
