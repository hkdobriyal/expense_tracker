import confetti from 'canvas-confetti'

/**
 * Triggers a dual-cannon celebratory confetti burst (used on transaction add, goal reached, sync).
 */
export function fireCelebrationConfetti() {
  try {
    const count = 160
    const defaults = {
      origin: { y: 0.75 },
      zIndex: 99999,
    }

    function fire(particleRatio, opts) {
      confetti({
        ...defaults,
        ...opts,
        particleCount: Math.floor(count * particleRatio),
      })
    }

    fire(0.25, {
      spread: 26,
      startVelocity: 55,
      colors: ['#7ef0c2', '#8ae6ff', '#ffd8a8'],
    })
    fire(0.2, {
      spread: 60,
      colors: ['#b29bff', '#ff8fab', '#8ae6ff'],
    })
    fire(0.35, {
      spread: 100,
      decay: 0.91,
      scalar: 0.8,
      colors: ['#7ef0c2', '#ffd8a8', '#ffffff'],
    })
    fire(0.1, {
      spread: 120,
      startVelocity: 25,
      decay: 0.92,
      scalar: 1.2,
      colors: ['#ffd8a8', '#ffb703'],
    })
    fire(0.1, {
      spread: 120,
      startVelocity: 45,
      colors: ['#8ae6ff', '#7ef0c2'],
    })
  } catch {
    // Graceful fallback if canvas is not supported
  }
}

/**
 * Rapid gold coin / wealth sparkle burst
 */
export function fireGoldBurst() {
  try {
    confetti({
      particleCount: 75,
      spread: 70,
      origin: { y: 0.6 },
      colors: ['#ffd8a8', '#ffb703', '#f48c06', '#ffe8d6'],
      ticks: 200,
      gravity: 1.1,
      decay: 0.94,
      startVelocity: 32,
      zIndex: 99999,
    })
  } catch {
    // fallback
  }
}
