// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';
import { TextDecoder, TextEncoder } from 'util';

// React Router 7 uses the Web Encoding API. CRA 5's jsdom environment does
// not expose it even though the active Node runtime does.
Object.assign(globalThis, { TextEncoder, TextDecoder });
