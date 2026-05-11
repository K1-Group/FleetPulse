// Service Worker Registration
export async function registerServiceWorker(): Promise<void> {
  if ('serviceWorker' in navigator && import.meta.env.PROD) {
    try {
      console.log('FleetPulse: Registering service worker...');
      
      const registration = await navigator.serviceWorker.register('/sw.js', {
        scope: '/'
      });

      console.log('FleetPulse: Service worker registered successfully:', registration);

      registration.update().catch((error) => {
        console.error('FleetPulse: Service worker update check failed:', error);
      });

      if (registration.waiting) {
        registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      }

      // Handle service worker updates
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        if (newWorker) {
          console.log('FleetPulse: New service worker found, installing...');
          
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              console.log('FleetPulse: New content available, activating now');
              newWorker.postMessage({ type: 'SKIP_WAITING' });
            }
          });
        }
      });

      // Listen for controlling service worker changes
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        console.log('FleetPulse: Service worker controller changed');
        window.location.reload();
      });

    } catch (error) {
      console.error('FleetPulse: Service worker registration failed:', error);
    }
  } else if (import.meta.env.DEV) {
    console.log('FleetPulse: Service worker registration skipped in development mode');
  } else {
    console.log('FleetPulse: Service workers not supported in this browser');
  }
}

// Check for service worker updates
export function checkForSWUpdate(): void {
  if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
    navigator.serviceWorker.getRegistration().then((registration) => {
      if (registration) {
        registration.update();
      }
    });
  }
}

// Unregister service worker (for development/debugging)
export async function unregisterServiceWorker(): Promise<void> {
  if ('serviceWorker' in navigator) {
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) {
        await registration.unregister();
        console.log('FleetPulse: Service worker unregistered');
      }
    } catch (error) {
      console.error('FleetPulse: Service worker unregistration failed:', error);
    }
  }
}
