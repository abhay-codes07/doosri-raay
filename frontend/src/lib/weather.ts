import { KEYS, readJson, writeJson } from './storage';

export interface GeoPoint {
  lat: number;
  lon: number;
  name: string;
}

export interface Weather {
  tempC: number;
  code: number;
  fetchedAt: string;
  place: string;
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;

export async function geocodeCity(city: string): Promise<GeoPoint | null> {
  const trimmed = city.trim();
  if (!trimmed) return null;
  const cached = readJson<GeoPoint | null>(KEYS.geocode(trimmed), null);
  if (cached) return cached;
  const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(trimmed)}&count=1&language=en&format=json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`geocode ${res.status}`);
  const data: unknown = await res.json();
  if (!isRecord(data) || !Array.isArray(data.results) || data.results.length === 0) return null;
  const first: unknown = data.results[0];
  if (!isRecord(first) || typeof first.latitude !== 'number' || typeof first.longitude !== 'number') return null;
  const point: GeoPoint = {
    lat: first.latitude,
    lon: first.longitude,
    name: typeof first.name === 'string' ? first.name : trimmed,
  };
  writeJson(KEYS.geocode(trimmed), point);
  return point;
}

export async function fetchWeather(city: string): Promise<Weather | null> {
  const cached = readJson<Weather | null>(KEYS.weather(city), null);
  if (cached && Date.now() - new Date(cached.fetchedAt).getTime() < 30 * 60 * 1000) return cached;
  const point = await geocodeCity(city);
  if (!point) return null;
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${point.lat}&longitude=${point.lon}&current=temperature_2m,weather_code&timezone=Asia%2FKolkata`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`forecast ${res.status}`);
  const data: unknown = await res.json();
  if (!isRecord(data) || !isRecord(data.current)) return null;
  const cur = data.current;
  if (typeof cur.temperature_2m !== 'number' || typeof cur.weather_code !== 'number') return null;
  const w: Weather = {
    tempC: cur.temperature_2m,
    code: cur.weather_code,
    fetchedAt: new Date().toISOString(),
    place: point.name,
  };
  writeJson(KEYS.weather(city), w);
  return w;
}

/** Stale cache regardless of age (offline fallback). */
export function staleWeather(city: string): Weather | null {
  return readJson<Weather | null>(KEYS.weather(city), null);
}

export interface WeatherLabel {
  hi: string;
  en: string;
  icon: string;
}

/** WMO weather interpretation codes → gentle Hindi/English labels. */
export function describeWeatherCode(code: number): WeatherLabel {
  if (code === 0) return { hi: 'साफ़ आसमान', en: 'Clear sky', icon: '☀️' };
  if (code === 1) return { hi: 'ज़्यादातर साफ़', en: 'Mostly clear', icon: '🌤️' };
  if (code === 2) return { hi: 'थोड़े बादल', en: 'Partly cloudy', icon: '⛅' };
  if (code === 3) return { hi: 'बादल छाए हैं', en: 'Overcast', icon: '☁️' };
  if (code === 45 || code === 48) return { hi: 'कोहरा', en: 'Fog', icon: '🌫️' };
  if (code >= 51 && code <= 57) return { hi: 'हल्की बूंदाबांदी', en: 'Drizzle', icon: '🌦️' };
  if (code >= 61 && code <= 67) return { hi: 'बारिश', en: 'Rain', icon: '🌧️' };
  if (code >= 71 && code <= 77) return { hi: 'बर्फ़बारी', en: 'Snow', icon: '🌨️' };
  if (code >= 80 && code <= 82) return { hi: 'बारिश की बौछारें', en: 'Rain showers', icon: '🌧️' };
  if (code >= 85 && code <= 86) return { hi: 'बर्फ़ की बौछारें', en: 'Snow showers', icon: '🌨️' };
  if (code >= 95) return { hi: 'आंधी-तूफ़ान', en: 'Thunderstorm', icon: '⛈️' };
  return { hi: 'मौसम', en: 'Weather', icon: '🌡️' };
}
