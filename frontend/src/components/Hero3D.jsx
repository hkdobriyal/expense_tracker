import { Canvas, useFrame } from '@react-three/fiber'
import { useReducedMotion } from 'framer-motion'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

// Decorative only. Colour reflects the real sign of this period's cash flow;
// no financial value is invented or shown here. `progress` (0–1, e.g. page
// scroll) tilts, spins and zooms the scene for scroll-driven 3D effects.
function Gyro({ positive, progress }) {
  const group = useRef()
  const a = useRef()
  const b = useRef()
  const c = useRef()
  const core = useRef()
  const primary = positive ? '#8ae6ff' : '#ff8fab'
  const secondary = positive ? '#7ef0c2' : '#ffd8a8'
  useFrame((state, delta) => {
    if (!group.current) return
    const p = progress?.get?.() ?? 0
    group.current.rotation.x = THREE.MathUtils.lerp(group.current.rotation.x, state.pointer.y * 0.35 + p * 1.2, 0.06)
    group.current.rotation.y = THREE.MathUtils.lerp(group.current.rotation.y, state.pointer.x * 0.45 + p * Math.PI, 0.06)
    const s = 1 + p * 0.35
    group.current.scale.lerp(new THREE.Vector3(s, s, s), 0.08)
    a.current.rotation.z += delta * (0.4 + p)
    b.current.rotation.x += delta * (0.5 + p)
    c.current.rotation.y += delta * (0.3 + p)
    core.current.rotation.y += delta * 0.3
    core.current.position.y = Math.sin(state.clock.elapsedTime * 1.4) * 0.06
  })
  return (
    <group ref={group}>
      <group ref={a}><mesh><torusGeometry args={[1.5, 0.03, 16, 120]} /><meshStandardMaterial color={primary} emissive={primary} emissiveIntensity={0.45} metalness={0.8} roughness={0.2} /></mesh></group>
      <group ref={b} rotation={[Math.PI / 4, 0, 0]}><mesh><torusGeometry args={[1.18, 0.03, 16, 100]} /><meshStandardMaterial color="#b29bff" emissive="#4d3580" emissiveIntensity={0.6} metalness={0.8} roughness={0.25} /></mesh></group>
      <group ref={c} rotation={[0, 0, Math.PI / 3]}><mesh><torusGeometry args={[0.88, 0.025, 16, 80]} /><meshStandardMaterial color={secondary} emissive={secondary} emissiveIntensity={0.5} /></mesh></group>
      <mesh ref={core}><icosahedronGeometry args={[0.42, 1]} /><meshStandardMaterial color={primary} emissive={primary} emissiveIntensity={0.35} metalness={0.9} roughness={0.15} flatShading /></mesh>
      <Coins />
      <Dust />
    </group>
  )
}

// A few orbiting "coins" for depth.
function Coins() {
  const ref = useRef()
  const coins = useMemo(() => Array.from({ length: 5 }, (_, i) => ({ angle: (i / 5) * Math.PI * 2, r: 2 + (i % 2) * 0.25, y: ((i % 3) - 1) * 0.35 })), [])
  useFrame((state) => { if (ref.current) ref.current.rotation.y = state.clock.elapsedTime * 0.18 })
  return (
    <group ref={ref}>
      {coins.map((coin, i) => (
        <mesh key={i} position={[Math.cos(coin.angle) * coin.r, coin.y, Math.sin(coin.angle) * coin.r]} rotation={[Math.PI / 2, 0, coin.angle]}>
          <cylinderGeometry args={[0.13, 0.13, 0.03, 32]} />
          <meshStandardMaterial color="#ffd8a8" emissive="#6b4a1a" emissiveIntensity={0.5} metalness={1} roughness={0.25} />
        </mesh>
      ))}
    </group>
  )
}

function Dust() {
  const ref = useRef()
  const positions = useMemo(() => {
    // Deterministic golden-angle distribution (no randomness needed for decoration).
    const count = 70
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const t = i / count
      const r = 1.4 + (i % 7) * 0.22
      const theta = i * 2.399963
      const phi = Math.acos(1 - 2 * t) - Math.PI / 2
      pos[i * 3] = r * Math.cos(theta) * Math.cos(phi)
      pos[i * 3 + 1] = r * Math.sin(phi) * 0.6
      pos[i * 3 + 2] = r * Math.sin(theta) * Math.cos(phi)
    }
    return pos
  }, [])
  useFrame((_, d) => { if (ref.current) ref.current.rotation.y += d * 0.08 })
  return (
    <points ref={ref}>
      <bufferGeometry><bufferAttribute attach="attributes-position" count={positions.length / 3} array={positions} itemSize={3} /></bufferGeometry>
      <pointsMaterial size={0.035} color="#8ae6ff" transparent opacity={0.7} sizeAttenuation />
    </points>
  )
}

export default function Hero3D({ positive = true, className = 'hero-canvas', progress }) {
  const reduce = useReducedMotion()
  return (
    <div className={className} aria-hidden>
      <Canvas frameloop={reduce ? 'demand' : 'always'} dpr={[1, 1.6]} camera={{ position: [0, 0, 4.6], fov: 45 }} gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }}>
        <ambientLight intensity={0.5} />
        <pointLight position={[3, 3, 4]} intensity={1.4} />
        <pointLight position={[-4, -2, -2]} intensity={0.8} color="#b29bff" />
        <Gyro positive={positive} progress={progress} />
      </Canvas>
    </div>
  )
}
