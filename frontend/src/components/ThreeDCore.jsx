import React, { useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { money } from '../lib/format'
import { playClick } from '../lib/sound'

// Mode 1: Multi-Ring Kinetic Gyroscope
function KineticGyroscope({ isPositive }) {
  const groupRef = useRef()
  const ring1Ref = useRef()
  const ring2Ref = useRef()
  const ring3Ref = useRef()
  const coreRef = useRef()

  const primaryColor = isPositive ? '#8ae6ff' : '#ff8fab'
  const secondaryColor = isPositive ? '#7ef0c2' : '#ffd8a8'
  const emissiveColor = isPositive ? '#16425b' : '#4a1525'

  useFrame((state, delta) => {
    // Parallax tilt from mouse pointer
    if (groupRef.current) {
      groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, state.pointer.y * 0.35, 0.05)
      groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, state.pointer.x * 0.45, 0.05)
    }
    // Independent multi-axis rotations
    if (ring1Ref.current) ring1Ref.current.rotation.z += delta * 0.45
    if (ring2Ref.current) ring2Ref.current.rotation.x += delta * 0.55
    if (ring3Ref.current) ring3Ref.current.rotation.y += delta * 0.35
    if (coreRef.current) {
      coreRef.current.rotation.y += delta * 0.2
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 2.5) * 0.08
      coreRef.current.scale.set(pulse, pulse, pulse)
    }
  })

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      {/* Outer Ring */}
      <group ref={ring1Ref}>
        <mesh>
          <torusGeometry args={[1.5, 0.032, 16, 100]} />
          <meshStandardMaterial color={primaryColor} metalness={0.8} roughness={0.2} emissive={primaryColor} emissiveIntensity={0.4} />
        </mesh>
        <mesh position={[1.5, 0, 0]}>
          <sphereGeometry args={[0.09, 16, 16]} />
          <meshStandardMaterial color={secondaryColor} emissive={secondaryColor} emissiveIntensity={1} />
        </mesh>
      </group>

      {/* Middle Ring */}
      <group ref={ring2Ref} rotation={[Math.PI / 4, 0, 0]}>
        <mesh>
          <torusGeometry args={[1.2, 0.035, 16, 80]} />
          <meshStandardMaterial color="#b29bff" metalness={0.7} roughness={0.3} emissive="#3d2b6b" emissiveIntensity={0.5} />
        </mesh>
        <mesh position={[0, 1.2, 0]}>
          <sphereGeometry args={[0.08, 16, 16]} />
          <meshStandardMaterial color={primaryColor} emissive={primaryColor} emissiveIntensity={0.8} />
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
          <meshStandardMaterial color="#ffd8a8" emissive="#ffd8a8" emissiveIntensity={0.9} />
        </mesh>
      </group>

      {/* Glowing Pulsing Energy Core */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.44, 32, 32]} />
        <meshStandardMaterial
          color={primaryColor}
          emissive={emissiveColor}
          emissiveIntensity={1.2}
          roughness={0.1}
          metalness={0.4}
          wireframe={false}
        />
      </mesh>
    </group>
  )
}

// Mode 2: 3D Floating Crystal Rupee Gem
function RupeeCrystal({ isPositive }) {
  const meshRef = useRef()
  const primaryColor = isPositive ? '#7ef0c2' : '#ff8fab'

  useFrame((state, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.6
      meshRef.current.rotation.x = THREE.MathUtils.lerp(meshRef.current.rotation.x, state.pointer.y * 0.4, 0.05)
      meshRef.current.position.y = Math.sin(state.clock.elapsedTime * 1.8) * 0.12
    }
  })

  return (
    <group>
      <mesh ref={meshRef}>
        <octahedronGeometry args={[1.05, 0]} />
        <meshStandardMaterial
          color={primaryColor}
          emissive={primaryColor}
          emissiveIntensity={0.6}
          roughness={0.15}
          metalness={0.85}
          wireframe={false}
        />
      </mesh>
      {/* Orbiting Halo Ring */}
      <mesh rotation={[Math.PI / 2.5, 0, 0]}>
        <torusGeometry args={[1.4, 0.02, 16, 80]} />
        <meshBasicMaterial color="#8ae6ff" />
      </mesh>
    </group>
  )
}

// Mode 3: 3D Holographic Platinum Card
function PlatinumCard() {
  const cardRef = useRef()

  useFrame((state, delta) => {
    if (cardRef.current) {
      cardRef.current.rotation.y = THREE.MathUtils.lerp(cardRef.current.rotation.y, state.pointer.x * 0.6 + Math.sin(state.clock.elapsedTime * 0.8) * 0.2, 0.05)
      cardRef.current.rotation.x = THREE.MathUtils.lerp(cardRef.current.rotation.x, -state.pointer.y * 0.5 + 0.2, 0.05)
      cardRef.current.position.y = Math.sin(state.clock.elapsedTime * 1.5) * 0.08
    }
  })

  return (
    <group ref={cardRef} rotation={[0.2, 0.3, -0.05]}>
      {/* Card Body */}
      <mesh>
        <boxGeometry args={[2.2, 1.4, 0.06]} />
        <meshStandardMaterial
          color="#152438"
          metalness={0.9}
          roughness={0.15}
          emissive="#0d1b2a"
          emissiveIntensity={0.6}
        />
      </mesh>
      {/* Golden Chip */}
      <mesh position={[-0.6, 0.15, 0.035]}>
        <boxGeometry args={[0.36, 0.28, 0.02]} />
        <meshStandardMaterial color="#ffd8a8" metalness={0.95} roughness={0.1} emissive="#e0a96d" emissiveIntensity={0.8} />
      </mesh>
      {/* Contactless waves emblem */}
      <mesh position={[0.7, 0.4, 0.035]}>
        <ringGeometry args={[0.08, 0.12, 16]} />
        <meshBasicMaterial color="#8ae6ff" />
      </mesh>
    </group>
  )
}

// Orbiting 3D Dust Particles
function OrbitingDust() {
  const dustRef = useRef()
  const count = 35
  const positions = React.useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const radius = 1.3 + Math.random() * 1.2
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
      dustRef.current.rotation.y += delta * 0.1
    }
  })

  return (
    <points ref={dustRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.035} color="#8ae6ff" transparent opacity={0.65} sizeAttenuation />
    </points>
  )
}

export function ThreeDCore({ cashflow = 0, invested = 0, billsDue = 0 }) {
  const [visualMode, setVisualMode] = useState('gyro')
  const isPositive = cashflow >= 0

  function switchMode() {
    playClick()
    setVisualMode((prev) => (prev === 'gyro' ? 'crystal' : prev === 'crystal' ? 'card' : 'gyro'))
  }

  const modeLabels = {
    gyro: '3D Gyroscope',
    crystal: '3D Rupee Crystal',
    card: '3D Holographic Card',
  }

  return (
    <div className="three-d-hero-container">
      {/* Interactive 3D Canvas */}
      <div className="three-d-canvas-wrap">
        <Canvas camera={{ position: [0, 0, 4.3], fov: 45 }}>
          <ambientLight intensity={0.6} />
          <pointLight position={[4, 4, 5]} color={isPositive ? '#8ae6ff' : '#ff8fab'} intensity={1.5} />
          <pointLight position={[-4, -3, 3]} color="#b29bff" intensity={0.8} />
          <directionalLight position={[0, 6, 2]} intensity={0.7} />

          {visualMode === 'gyro' && <KineticGyroscope isPositive={isPositive} />}
          {visualMode === 'crystal' && <RupeeCrystal isPositive={isPositive} />}
          {visualMode === 'card' && <PlatinumCard />}
          <OrbitingDust />
        </Canvas>
      </div>

      {/* Floating Holographic HUD Stats */}
      <div className="hologram-hud-badges">
        <div className="hud-badge hud-left">
          <span className="hud-label">NET CASHFLOW</span>
          <strong className={isPositive ? 'positive' : 'negative'}>{money(cashflow)}</strong>
          <small>{isPositive ? 'Surplus in motion' : 'Spend ahead of income'}</small>
        </div>

        <div className="hud-badge hud-right">
          <span className="hud-label">INVESTED WEALTH</span>
          <strong>{money(invested)}</strong>
          <small>SIPs & equity</small>
        </div>

        <div className="hud-badge hud-bottom">
          <span className="hud-label">UPCOMING BILLS</span>
          <strong>{money(billsDue)}</strong>
          <small>Committed</small>
        </div>
      </div>

      {/* Interactive Mode Selector Button */}
      <button className="three-d-mode-pill" onClick={switchMode} title="Click to cycle 3D visual">
        <span className="mode-dot" style={{ background: isPositive ? '#7ef0c2' : '#ff8fab' }} />
        <span>{modeLabels[visualMode]}</span>
        <span className="mode-hint">↺</span>
      </button>
    </div>
  )
}
export default ThreeDCore
