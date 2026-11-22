/**
 * static/js/main.js - Core UI interactions and state management
 */

// Mobile Sidebar Toggle
function toggleMobileSidebar() {
  const sidebar = document.getElementById('appSidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  if (sidebar) {
    sidebar.classList.toggle('open');
  }
  if (backdrop) {
    backdrop.classList.toggle('active');
  }
}

// Global Language Switcher (EN vs HI)
let currentAppLanguage = localStorage.getItem('kisaan_app_lang') || 'en';

function switchGlobalLanguage(lang) {
  currentAppLanguage = lang;
  localStorage.setItem('kisaan_app_lang', lang);

  const btnEn = document.getElementById('btnLangEn');
  const btnHi = document.getElementById('btnLangHi');

  if (btnEn && btnHi) {
    if (lang === 'hi') {
      btnHi.classList.add('active');
      btnEn.classList.remove('active');
    } else {
      btnEn.classList.add('active');
      btnHi.classList.remove('active');
    }
  }

  // Update widget language as well
  const widgetSelect = document.getElementById('widgetLangSelect');
  if (widgetSelect) {
    widgetSelect.value = lang;
  }
}

// Auto-dismiss Flash Alerts
document.addEventListener('DOMContentLoaded', () => {
  const toasts = document.querySelectorAll('.alert-toast');
  toasts.forEach(toast => {
    setTimeout(() => {
      toast.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px)';
      setTimeout(() => toast.remove(), 400);
    }, 4500);
  });
});
