import { useEffect, useState } from 'react'
import { headshotUrl, initials, usePlayerImages } from '../lib/playerImages'

/** Round headshot (ESPN CDN) looked up by identityKey(canonicalName, position);
 * falls back to initials when the player has no id or the image fails. */
export default function PlayerAvatar({
  playerKey,
  name,
  size = 32,
}: {
  playerKey: string
  name: string
  /** Diameter in px. */
  size?: number
}) {
  const images = usePlayerImages()
  const id = images?.get(playerKey)
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [id])

  return (
    <span
      className="player-avatar"
      style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.36)) }}
    >
      {id && !failed ? (
        <img src={headshotUrl(id)} alt={name} loading="lazy" onError={() => setFailed(true)} />
      ) : (
        initials(name)
      )}
    </span>
  )
}
