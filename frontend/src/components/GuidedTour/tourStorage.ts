const TOUR_STORAGE_KEY = 'octowatch_tour_completed';

/** Check if the guided tour has been completed. */
export function isTourCompleted(): boolean {
  return localStorage.getItem(TOUR_STORAGE_KEY) === 'true';
}

/** Reset the tour so it shows again on next page load. */
export function resetTour(): void {
  localStorage.removeItem(TOUR_STORAGE_KEY);
}
