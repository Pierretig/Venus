document.addEventListener('DOMContentLoaded', function() {
  const termsVersion = '1.0';
  const consent = document.getElementById('terms-consent');
  const acceptedVersion = localStorage.getItem('terms_version');
  if (consent && (localStorage.getItem('terms_accepted') !== 'true' || acceptedVersion !== termsVersion)) {
    window.setTimeout(() => { consent.hidden = false; }, 1200);
  }
  document.getElementById('terms-accept')?.addEventListener('click', () => {
    localStorage.setItem('terms_accepted', 'true');
    localStorage.setItem('terms_version', termsVersion);
    if (consent) consent.hidden = true;
  });

  // Sélecteur d'étoiles interactif (produits et avis général accueil)
  document.querySelectorAll('.star-rating-selector').forEach(container => {
    const form = container.closest('form');
    const ratingInput = form ? form.querySelector('#id_rating_input') : document.getElementById('id_rating_input');
    const stars = container.querySelectorAll('.star-btn');
    if (ratingInput && stars.length > 0) {
      if (!ratingInput.value) ratingInput.value = "5";
      stars.forEach(star => {
        star.addEventListener('click', function() {
          const selectedVal = parseInt(this.dataset.value, 10);
          ratingInput.value = selectedVal.toString();
          stars.forEach(s => {
            const sVal = parseInt(s.dataset.value, 10);
            if (sVal <= selectedVal) {
              s.classList.remove('text-muted');
              s.classList.add('text-warning');
            } else {
              s.classList.remove('text-warning');
              s.classList.add('text-muted');
            }
          });
        });
      });
    }
  });

    
    // 1. Configuration de l'observateur
    const observerOptions = {
        threshold: 0.15, // Déclenche quand 15% de l'élément est visible
        rootMargin: "0px 0px -50px 0px" // Déclenche un peu avant que l'élément n'entre totalement
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // On active l'élément
                const el = entry.target;
                el.style.opacity = "1";
                el.style.transform = "translateY(0)";
                
                // Une fois animé, on arrête d'observer cet élément (gain de performance)
                observer.unobserve(el);
            }
        });
    }, observerOptions);

    // 2. Sélection des éléments à animer
    // On évite de cibler tout le <main> pour ne pas masquer la page complète
    const elementsToAnimate = document.querySelectorAll('.col-lg-4, .col-lg-2, .col-lg-3, .section-title, .card');

    elementsToAnimate.forEach(el => {
        // État initial (caché)
        el.style.opacity = "0";
        el.style.transform = "translateY(30px)";
        el.style.transition = "opacity 0.8s cubic-bezier(0.165, 0.84, 0.44, 1), transform 0.8s cubic-bezier(0.165, 0.84, 0.44, 1)";
        
        // On lance l'observation
        observer.observe(el);
    });

    console.log("✨ Scroll Reveal activé avec succès !");
});

document.addEventListener('DOMContentLoaded', () => {
    const zoneSelect = document.getElementById('zone-select');
    const shippingDisplay = document.getElementById('shipping-cost');
    const totalDisplay = document.getElementById('grand-total');
    const subtotalEl = document.getElementById('subtotal-value');

    if (zoneSelect && shippingDisplay && totalDisplay && subtotalEl) {
        zoneSelect.addEventListener('change', function() {
            const shipPrice = parseInt(this.value, 10) || 0;
            const subTotal = parseInt(subtotalEl.dataset.subtotal || "0", 10) || 0;
            
            shippingDisplay.innerText = shipPrice + " XOF";
            totalDisplay.innerText = (subTotal + shipPrice) + " XOF";
        });
    }
});

// Navbar sticky - hide on scroll down, show on scroll up
let lastScrollTop = 0;
const navbar = document.querySelector('.custom-navbar');
window.addEventListener('scroll', () => {
  if (!navbar) return;
  let scrollTop = window.pageYOffset || document.documentElement.scrollTop;
  if (scrollTop > lastScrollTop && scrollTop > 100) {
    navbar.style.transform = 'translateY(-100%)';
  } else {
    navbar.style.transform = 'translateY(0)';
  }
  lastScrollTop = scrollTop;
});

// Panier en temps réel sur toutes les pages
document.addEventListener('DOMContentLoaded', () => {
  const badges = document.querySelectorAll('.js-cart-badge');
  if (!badges.length) return;

  const refreshCartCount = async () => {
    try {
      const response = await fetch('/orders/cart/count/', {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
      });
      if (!response.ok) return;
      const data = await response.json();
      const count = Number.isFinite(data.count) ? data.count : 0;
      badges.forEach((badge) => {
        badge.textContent = String(count);
      });
    } catch (error) {
      // Silence volontaire : ne pas dégrader l'UX en cas de micro-coupure réseau.
    }
  };

  refreshCartCount();
  setInterval(refreshCartCount, 8000);
});

// ================= PROTECTION IMAGES (WATERMARK) =================
// Bloque le clic droit et le drag sur les images protégées
// tout en préservant la navigation normale du site.

document.addEventListener('DOMContentLoaded', () => {
  const protectedImages = document.querySelectorAll('img.protected-image');

  protectedImages.forEach((img) => {
    // Empêche le menu contextuel (clic droit → enregistrer l'image)
    img.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      return false;
    });

    // Empêche le drag & drop de l'image
    img.addEventListener('dragstart', (e) => {
      e.preventDefault();
      return false;
    });

    // Empêche la copie via touche
    img.addEventListener('copy', (e) => {
      e.preventDefault();
      return false;
    });
  });

  console.log('🔒 Protection images activée');
});

// ================= FIN PROTECTION IMAGES =================
