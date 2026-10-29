import { useEffect, useState } from "react";

/** Count whole elapsed seconds while a request is active. */
export function useElapsedTime(isRunning) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(
    function trackElapsedSeconds() {
      setElapsedSeconds(0);
      if (!isRunning) {
        return undefined;
      }

      const intervalId = window.setInterval(function incrementElapsedSeconds() {
        setElapsedSeconds((currentSeconds) => currentSeconds + 1);
      }, 1000);

      return function stopElapsedTimer() {
        window.clearInterval(intervalId);
      };
    },
    [isRunning],
  );

  return elapsedSeconds;
}
