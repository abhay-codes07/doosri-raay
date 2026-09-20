import { useEffect, useState } from 'react';
import { subscribeActivity } from '../lib/activity';

/**
 * 3 px bar along the top edge that sweeps while any poll or request is in flight. Purely
 * decorative (aria-hidden): the cards already announce their own loading states.
 */
export function ProgressBar() {
  const [active, setActive] = useState(0);
  useEffect(() => subscribeActivity(setActive), []);
  return <div className={`progress-bar ${active > 0 ? 'on' : ''}`} aria-hidden="true" />;
}
