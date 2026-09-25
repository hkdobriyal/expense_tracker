import React, { useRef, useState, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { money } from '../lib/format'
import { playClick, playCoin } from '../lib/sound'
import { fireGoldBurst } from '../lib/confetti'

// Mode 1: Multi-Ring Kinetic Gyroscope with Interactive Pulse
function KineticGyroscope({ isPositive, shockwave, onInteract }) {
  const groupRef = useRef()
  const ring1Ref = useRef()
  const ring2Ref = useRef()
  const ring3Ref = useRef()
  const coreRef = useRef()

  const primaryColor = isPositive ? '#8ae6ff' : '#ff8fab'
  const secondaryColor = isPositive ? '#7ef0c2' : '#ffd8a8'
  const emissiveColor = isPositive ? '#16425b' : '#4a1525'

  useFrame((state, delta) => {
    // Smooth mouse parallax tilt
    if (groupRef.current) {
      groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, state.pointer.y * 0.4, 0.05)
      groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, state.pointer.x * 0.5, 0.05)
    }
    // Multi-axis kinetic spin
    if (ring1Ref.current) ring1Ref.current.rotation.z += delta * (0.45 + (shockwave ? 1.5 : 0))
    if (ring2Ref.current) ring2Ref.current.rotation.x += delta * (0.55 + (shockwave ? 1.5 : 0))
    if (ring3Ref.current) ring3Ref.current.rotation.y += delta * (0.35 + (shockwave ? 1.5 : 0))
    if (coreRef.current) {
      coreRef.current.rotation.y += delta * 0.25
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 2.5) * 0.08 + (shockwave ? 0.35 : 0)
      coreRef.current.scale.set(pulse, pulse, pulse)
    }
  })

  return (
    <group ref={groupRef} onClick={onInteract} cursor="pointer">
      {/* Outer Gyro Ring */}
      <group ref={ring1Ref}>
        <mesh>
          <torusGeometry args={[1.5, 0.034, 16, 100]} />
          <meshStandardMaterial color={primaryColor} metalness={0.85} roughness={0.2} emissive={primaryColor} emissiveIntensity={shockwave ? 1.2 : 0.4} />
        </mesh>
        <mesh position={[1.5, 0, 0]}>
          <sphereGeometry args={[0.09, 16, 16]} />
          <meshStandardMaterial color={secondaryColor} emissive={secondaryColor} emissiveIntensity={1.2} />
        </mesh>
      </group>

      {/* Middle Ring */}
      <group ref={ring2Ref} rotation={[Math.PI / 4, 0, 0]}>
        <mesh>
          <torusGeometry args={[1.2, 0.035, 16, 80]} />
          <meshStandardMaterial color="#b29bff" metalness={0.75} roughness={0.25} emissive="#4d3580" emissiveIntensity={shockwave ? 1.0 : 0.5} />
        </mesh>
        <mesh position={[0, 1.2, 0]}>
          <sphereGeometry args={[0.08, 16, 16]} />
          <meshStandardMaterial color={primaryColor} emissive={primaryColor} emissiveIntensity={1.0} />
        </mesh>
      </group>

      {/* Inner Ring */}
      <group ref={ring3Ref} rotation={[0, Math.PI / 3, 0]}>
        <mesh>
          <torusGeometry args={[0.9, 0.03, 16, 64]} />
          <meshStandardMaterial color={secondaryColor} metalness={0.8} roughness={0.2} emissive={secondaryColor} emissiveIntensity={0.4} />
        </mesh>
        <mesh position={[-0.9, 0, 0]}>
          <sphereGeometry args={[0.07, 16, 16]} />
          <meshStandardMaterial color="#ffd8a8" emissive="#ffd8a8" emissiveIntensity={1.1} />
        </mesh>
      </group>

      {/* Glowing Energy Core */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.44, 32, 32]} />
        <meshStandardMaterial
          color={primaryColor}
          emissive={emissiveColor}
          emissiveIntensity={shockwave ? 2.5 : 1.3}
          roughness={0.1}
          metalness={0.5}
        />
      </mesh>
    </group>
  )
}

// Mode 2: 3D Floating Quantum Rupee Crystal
function RupeeCrystal({ isPositive, shockwave, onInteract }) {
  const groupRef = useRef()
  const meshRef = useRef()
  const primaryColor = isPositive ? '#7ef0c2' : '#ff8fab'

  useFrame((state, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, state.pointer.y * 0.4, 0.05)
      groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, state.pointer.x * 0.5, 0.05)
    }
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * (0.6 + (shockwave ? 2.0 : 0))
      meshRef.current.position.y = Math.sin(state.clock.elapsedTime * 1.8) * 0.14
      const scaleVal = 1 + (shockwave ? 0.3 : 0)
      meshRef.current.scale.set(scaleVal, scaleVal, scaleVal)
    }
  })

  return (
    <group ref={groupRef} onClick={onInteract} cursor="pointer">
      <mesh ref={meshRef}>
        <octahedronGeometry args={[1.05, 0]} />
        <meshStandardMaterial
          color={primaryColor}
          emissive={primaryColor}
          emissiveIntensity={shockwave ? 1.5 : 0.65}
          roughness={0.12}
          metalness={0.88}
        />
      </mesh>
      {/* Halo Ring */}
      <mesh rotation={[Math.PI / 2.5, 0, 0]}>
        <torusGeometry args={[1.45, 0.025, 16, 80]} />
        <meshStandardMaterial color="#8ae6ff" emissive="#8ae6ff" emissiveIntensity={0.8} />
      </mesh>
      {/* Outer Halo */}
      <mesh rotation={[-Math.PI / 3, Math.PI / 4, 0]}>
        <torusGeometry args={[1.7, 0.015, 16, 80]} />
        <meshStandardMaterial color="#ffd8a8" emissive="#ffd8a8" emissiveIntensity={0.5} />
      </mesh>
    </group>
  )
}

// Mode 3: 3D Holographic Platinum Card
function PlatinumCard({ shockwave, onInteract }) {
  const cardRef = useRef()

  useFrame((state, delta) => {
    if (cardRef.current) {
      cardRef.current.rotation.y = THREE.MathUtils.lerp(cardRef.current.rotation.y, state.pointer.x * 0.7 + Math.sin(state.clock.elapsedTime * 0.8) * 0.2, 0.05)
      cardRef.current.rotation.x = THREE.MathUtils.lerp(cardRef.current.rotation.x, -state.pointer.y * 0.6 + 0.2, 0.05)
      cardRef.current.position.y = Math.sin(state.clock.elapsedTime * 1.5) * 0.08
      const s = 1 + (shockwave ? 0.15 : 0)
      cardRef.current.scale.set(s, s, s)
    }
  })

  return (
    <group ref={cardRef} rotation={[0.2, 0.3, -0.05]} onClick={onInteract} cursor="pointer">
      {/* Card Body */}
      <mesh>
        <boxGeometry args={[2.3, 1.45, 0.07]} />
        <meshStandardMaterial
          color="#152438"
          metalness={0.92}
          roughness={0.15}
          emissive={shockwave ? '#1e3d59' : '#0d1b2a'}
          emissiveIntensity={shockwave ? 1.4 : 0.6}
        />
      </mesh>
      {/* Golden Smart Chip */}
      <mesh position={[-0.65, 0.15, 0.04]}>
        <boxGeometry args={[0.38, 0.3, 0.02]} />
        <meshStandardMaterial color="#ffd8a8" metalness={0.98} roughness={0.08} emissive="#e0a96d" emissiveIntensity={0.9} />
      </mesh>
      {/* Contactless waves emblem */}
      <mesh position={[0.75, 0.42, 0.04]}>
        <ringGeometry args={[0.08, 0.12, 24]} />
        <meshBasicMaterial color="#8ae6ff" />
      </mesh>
      {/* Embossed Card Strip */}
      <mesh position={[0, -0.35, 0.04]}>
        <boxGeometry args={[1.9, 0.12, 0.015]} />
        <meshStandardMaterial color="#7ef0c2" metalness={0.8} roughness={0.3} emissive="#7ef0c2" emissiveIntensity={0.6} />
      </mesh>
    </group>
  )
}

// Mode 4: Quantum Wealth Vortex with Floating Currency Runes
function QuantumVortex({ isPositive, shockwave, onInteract }) {
  const groupRef = useRef()
  const torus1Ref = useRef()
  const torus2Ref = useRef()
  const torus3Ref = useRef()

  const primaryColor = isPositive ? '#7ef0c2' : '#ff8fab'

  useFrame((state, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, state.pointer.y * 0.4, 0.05)
      groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, state.pointer.x * 0.5, 0.05)
    }
    if (torus1Ref.current) torus1Ref.current.rotation.z += delta * (0.8 + (shockwave ? 2.5 : 0))
    if (torus2Ref.current) torus2Ref.current.rotation.x += delta * (0.7 + (shockwave ? 2.0 : 0))
    if (torus3Ref.current) torus3Ref.current.rotation.y += delta * (0.6 + (shockwave ? 2.2 : 0))
  })

  return (
    <group ref={groupRef} onClick={onInteract} cursor="pointer">
      {/* Vortex Torus 1 */}
      <mesh ref={torus1Ref}>
        <torusGeometry args={[1.5, 0.03, 16, 80]} />
        <meshStandardMaterial color="#8ae6ff" metalness={0.9} roughness={0.1} emissive="#8ae6ff" emissiveIntensity={shockwave ? 1.5 : 0.7} />
      </mesh>
      {/* Vortex Torus 2 */}
      <mesh ref={torus2Ref} rotation={[Math.PI / 3, 0, Math.PI / 4]}>
        <torusGeometry args={[1.25, 0.035, 16, 70]} />
        <meshStandardMaterial color={primaryColor} metalness={0.8} roughness={0.2} emissive={primaryColor} emissiveIntensity={shockwave ? 1.6 : 0.8} />
      </mesh>
      {/* Vortex Torus 3 */}
      <mesh ref={torus3Ref} rotation={[-Math.PI / 3, Math.PI / 6, 0]}>
        <torusGeometry args={[1.0, 0.03, 16, 60]} />
        <meshStandardMaterial color="#ffd8a8" metalness={0.9} roughness={0.1} emissive="#ffd8a8" emissiveIntensity={shockwave ? 1.4 : 0.6} />
      </mesh>

      {/* Center Singularity Sphere */}
      <mesh scale={shockwave ? 1.35 : 1.0}>
        <sphereGeometry args={[0.38, 32, 32]} />
        <meshStandardMaterial color="#ffffff" emissive="#7ef0c2" emissiveIntensity={2.0} />
      </mesh>

      {/* Orbiting Satellites (Floating Wealth Gems) */}
      <mesh position={[1.2, 0.5, 0.3]}>
        <dodecahedronGeometry args={[0.12]} />
        <meshStandardMaterial color="#ffd8a8" emissive="#ffd8a8" emissiveIntensity={1.0} metalness={0.9} />
      </mesh>
      <mesh position={[-1.1, -0.6, -0.2]}>
        <dodecahedronGeometry args={[0.1]} />
        <meshStandardMaterial color="#8ae6ff" emissive="#8ae6ff" emissiveIntensity={1.0} metalness={0.9} />
      </mesh>
    </group>
  )
}

// Orbiting 3D Interactive Nebula Dust
function OrbitingNebula({ shockwave }) {
  const dustRef = useRef()
  const count = 55
  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const radius = 1.3 + Math.random() * 1.5
      const theta = Math.random() * Math.PI * 2
      const phi = (Math.random() - 0.5) * Math.PI
      pos[i * 3] = radius * Math.cos(theta) * Math.cos(phi)
      pos[i * 3 + 1] = radius * Math.sin(phi)
      pos[i * 3 + 2] = radius * Math.sin(theta) * Math.cos(phi)
    }
    return pos
  }, [])

  useFrame((_, delta) => {
    if (dustRef.current) {
      dustRef.current.rotation.y += delta * (0.12 + (shockwave ? 0.8 : 0))
      dustRef.current.rotation.x += delta * 0.04
    }
  })

  return (
    <points ref={dustRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={shockwave ? 0.055 : 0.038} color="#8ae6ff" transparent opacity={0.75} sizeAttenuation />
    </points>
  )
}

export function ThreeDCore({ cashflow = 0, invested = 0, billsDue = 0 }) {
  const [visualMode, setVisualMode] = useState('gyro')
  const [shockwave, setShockwave] = useState(false)
  const isPositive = cashflow >= 0

  function switchMode() {
    playClick()
    setVisualMode((prev) => {
      if (prev === 'gyro') return 'crystal'
      if (prev === 'crystal') return 'card'
      if (prev === 'card') return 'vortex'
      return 'gyro'
    })
  }

  function handleObjectClick() {
    playCoin()
    fireGoldBurst()
    setShockwave(true)
    setTimeout(() => setShockwave(false), 600)
  }

  const modeLabels = {
    gyro: '3D Kinetic Gyroscope',
    crystal: '3D Rupee Crystal',
    card: '3D Holographic Card',
    vortex: '3D Wealth Vortex',
  }

  return (
    <div className="three-d-hero-container">
      {/* Interactive 3D Canvas */}
      <div className="three-d-canvas-wrap" title="Hover to tilt • Click 3D core to trigger energy burst!">
        <Canvas camera={{ position: [0, 0, 4.3], fov: 45 }}>
          <ambientLight intensity={0.65} />
          <pointLight position={[4, 4, 5]} color={isPositive ? '#8ae6ff' : '#ff8fab'} intensity={shockwave ? 3.0 : 1.6} />
          <pointLight position={[-4, -3, 3]} color="#b29bff" intensity={shockwave ? 2.0 : 0.9} />
          <directionalLight position={[0, 6, 2]} intensity={0.7} />

          {visualMode === 'gyro' && <KineticGyroscope isPositive={isPositive} shockwave={shockwave} onInteract={handleObjectClick} />}
          {visualMode === 'crystal' && <RupeeCrystal isPositive={isPositive} shockwave={shockwave} onInteract={handleObjectClick} />}
          {visualMode === 'card' && <PlatinumCard shockwave={shockwave} onInteract={handleObjectClick} />}
          {visualMode === 'vortex' && <QuantumVortex isPositive={isPositive} shockwave={shockwave} onInteract={handleObjectClick} />}
          
          <OrbitingNebula shockwave={shockwave} />
        </Canvas>
      </div>

      {/* Floating Holographic HUD Stats */}
      <div className="hologram-hud-badges">
        <div className="hud-badge hud-left" onClick={handleObjectClick}>
          <span className="hud-label">NET CASHFLOW</span>
          <strong className={isPositive ? 'positive' : 'negative'}>{money(cashflow)}</strong>
          <small>{isPositive ? 'Surplus in motion' : 'Spend ahead of income'}</small>
        </div>

        <div className="hud-badge hud-right" onClick={handleObjectClick}>
          <span className="hud-label">INVESTED WEALTH</span>
          <strong>{money(invested)}</strong>
          <small>SIPs & equity</small>
        </div>

        <div className="hud-badge hud-bottom" onClick={handleObjectClick}>
          <span className="hud-label">UPCOMING BILLS</span>
          <strong>{money(billsDue)}</strong>
          <small>Committed dues</small>
        </div>
      </div>

      {/* Interactive 3D Mode & Action Bar */}
      <div className="three-d-controls-row">
        <button className="three-d-mode-pill" onClick={switchMode} title="Click to cycle 3D visual mode">
          <span className="mode-dot" style={{ background: isPositive ? '#7ef0c2' : '#ff8fab' }} />
          <span>{modeLabels[visualMode]}</span>
          <span className="mode-hint">↺ Cycle</span>
        </button>

        <button className="three-d-shockwave-pill" onClick={handleObjectClick} title="Trigger interactive 3D energy burst">
          <span>⚡ Shockwave</span>
        </button>
      </div>
    </div>
  )
}
export default ThreeDCore
