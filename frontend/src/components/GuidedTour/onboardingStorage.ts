import type { OnboardingResult } from './OnboardingWizard';

export const ONBOARDING_COMPLETE_STORAGE_KEY = 'octowatch-onboarding-complete';
export const ONBOARDING_PROFILE_STORAGE_KEY = 'octowatch-onboarding-profile';

export function isOnboardingComplete(): boolean {
  return localStorage.getItem(ONBOARDING_COMPLETE_STORAGE_KEY) === 'true';
}

export function persistOnboardingResult(result: OnboardingResult): void {
  localStorage.setItem(ONBOARDING_COMPLETE_STORAGE_KEY, 'true');
  localStorage.setItem(ONBOARDING_PROFILE_STORAGE_KEY, JSON.stringify(result));
}
