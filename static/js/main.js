document.addEventListener('DOMContentLoaded', function() {
    
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

    if (zoneSelect) {
        zoneSelect.addEventListener('change', function() {
            const shipPrice = parseInt(this.value);
            const subTotal = parseInt("{{ cart.get_total_price }}");
            
            shippingDisplay.innerText = shipPrice + " XOF";
            totalDisplay.innerText = (subTotal + shipPrice) + " XOF";
        });
    }
});