import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from 'framer-motion'
import { useRef } from 'react'

// Fade/slide in when scrolled into view (once).
export function Reveal({ children, delay = 0, y = 28, className = '', as = 'div', ...props }) {
  const reduce = useReducedMotion()
  const Tag = motion[as] || motion.div
  return (
    <Tag className={className} initial={reduce ? false : { opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }} {...props}>
      {children}
    </Tag>
  )
}

// Children revealed one after another.
export function Stagger({ children, className = '', gap = 0.08 }) {
  const reduce = useReducedMotion()
  return (
    <motion.div className={className} initial={reduce ? false : 'hidden'} whileInView="show" viewport={{ once: true, amount: 0.15 }}
      variants={{ hidden: {}, show: { transition: { staggerChildren: gap } } }}>
      {children}
    </motion.div>
  )
}

export const staggerItem = {
  hidden: { opacity: 0, y: 24, scale: 0.98 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
}

// 3D tilt that follows the pointer, with a moving highlight.
export function Tilt({ children, className = '', max = 8, style, ...props }) {
  const reduce = useReducedMotion()
  const ref = useRef(null)
  const rx = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 })
  const ry = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 })
  const gx = useMotionValue(50)
  const gy = useMotionValue(50)
  const glare = useTransform([gx, gy], ([x, y]) => `radial-gradient(420px circle at ${x}% ${y}%, rgba(255,255,255,.10), transparent 45%)`)
  if (reduce) return <div className={className} style={style} {...props}>{children}</div>
  const onMove = (e) => {
    const r = ref.current.getBoundingClientRect()
    const px = (e.clientX - r.left) / r.width
    const py = (e.clientY - r.top) / r.height
    ry.set((px - 0.5) * max * 2)
    rx.set(-(py - 0.5) * max * 2)
    gx.set(px * 100)
    gy.set(py * 100)
  }
  const reset = () => { rx.set(0); ry.set(0) }
  return (
    <motion.div ref={ref} className={`tilt ${className}`} onPointerMove={onMove} onPointerLeave={reset}
      style={{ rotateX: rx, rotateY: ry, transformPerspective: 900, transformStyle: 'preserve-3d', ...style }} {...props}>
      {children}
      <motion.span className="tilt-glare" style={{ background: glare }} aria-hidden />
    </motion.div>
  )
}

// Thin bar at the top showing how far the page has been scrolled.
export function ScrollProgress({ target }) {
  const { scrollYProgress } = useScroll(target ? { container: target } : undefined)
  const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 26 })
  return <motion.div className="scroll-progress" style={{ scaleX }} aria-hidden />
}

// Moves children at a different speed than the page while scrolling.
export function Parallax({ children, offset = 60, className = '' }) {
  const ref = useRef(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] })
  const y = useTransform(scrollYProgress, [0, 1], reduce ? [0, 0] : [offset, -offset])
  return <motion.div ref={ref} className={className} style={{ y }}>{children}</motion.div>
}
