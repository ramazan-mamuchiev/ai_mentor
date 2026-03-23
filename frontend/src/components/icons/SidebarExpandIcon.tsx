import type { SVGProps } from 'react'

interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number
}

/** Panel outline (left sidebar highlighted). Source: OpenAI SDK — SidebarOpenLeft */
export const SidebarExpandIcon = ({ size = 18, ...props }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path fillRule="evenodd" clipRule="evenodd" d="M10 5V19H18C18.5523 19 19 18.5523 19 18V6C19 5.44772 18.5523 5 18 5H10ZM3 6C3 4.34315 4.34315 3 6 3H18C19.6569 3 21 4.34315 21 6V18C21 19.6569 19.6569 21 18 21H6C4.34315 21 3 19.6569 3 18V6Z" />
  </svg>
)
