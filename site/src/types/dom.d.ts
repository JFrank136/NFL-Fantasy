// Augments React's input typings with the non-standard `webkitdirectory`
// attribute, which browsers support for folder-picker file inputs but
// which isn't part of the standard HTML/React type definitions.
import 'react'

declare module 'react' {
  interface InputHTMLAttributes<T> extends HTMLAttributes<T> {
    webkitdirectory?: string
  }
}
