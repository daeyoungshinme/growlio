import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import pngToIco from "png-to-ico";

const rootDir = dirname(dirname(fileURLToPath(import.meta.url)));
const faviconSvgPath = join(rootDir, "public", "favicon.svg");
const foregroundSvgPath = join(rootDir, "public", "favicon-foreground.svg");
const iconsDir = join(rootDir, "public", "icons");
const resDir = join(rootDir, "android", "app", "src", "main", "res");

const webSizes = [16, 32, 48, 180, 192, 512];

// Standard Android density scale factors (mdpi = 1x baseline).
const densities = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
const legacyBaseSize = 48; // mdpi ic_launcher.png / ic_launcher_round.png
const foregroundBaseSize = 108; // mdpi ic_launcher_foreground.png (adaptive icon canvas)

const SPLASH_BG = "#0F172A";
const splashSizes = {
  drawable: { w: 480, h: 320 },
  "drawable-land-mdpi": { w: 480, h: 320 },
  "drawable-land-hdpi": { w: 800, h: 480 },
  "drawable-land-xhdpi": { w: 1280, h: 720 },
  "drawable-land-xxhdpi": { w: 1600, h: 960 },
  "drawable-land-xxxhdpi": { w: 1920, h: 1280 },
  "drawable-port-mdpi": { w: 320, h: 480 },
  "drawable-port-hdpi": { w: 480, h: 800 },
  "drawable-port-xhdpi": { w: 720, h: 1280 },
  "drawable-port-xxhdpi": { w: 960, h: 1600 },
  "drawable-port-xxxhdpi": { w: 1280, h: 1920 },
};

async function generateWebIcons() {
  mkdirSync(iconsDir, { recursive: true });
  const svgBuffer = readFileSync(faviconSvgPath);

  const pngBuffers = {};
  for (const size of webSizes) {
    const buffer = await sharp(svgBuffer).resize(size, size).png().toBuffer();
    pngBuffers[size] = buffer;
    writeFileSync(join(iconsDir, `icon-${size}.png`), buffer);
    console.log(`generated icons/icon-${size}.png`);
  }

  const icoBuffer = await pngToIco([pngBuffers[16], pngBuffers[32], pngBuffers[48]]);
  writeFileSync(join(rootDir, "public", "favicon.ico"), icoBuffer);
  console.log("generated favicon.ico");
}

async function generateAndroidLauncherIcons() {
  const faviconSvgBuffer = readFileSync(faviconSvgPath);
  const foregroundSvgBuffer = readFileSync(foregroundSvgPath);

  for (const [density, scale] of Object.entries(densities)) {
    const legacySize = Math.round(legacyBaseSize * scale);
    const foregroundSize = Math.round(foregroundBaseSize * scale);
    const mipmapDir = join(resDir, `mipmap-${density}`);
    mkdirSync(mipmapDir, { recursive: true });

    const legacyBuffer = await sharp(faviconSvgBuffer).resize(legacySize, legacySize).png().toBuffer();
    writeFileSync(join(mipmapDir, "ic_launcher.png"), legacyBuffer);

    const circleMask = Buffer.from(
      `<svg width="${legacySize}" height="${legacySize}"><circle cx="${legacySize / 2}" cy="${legacySize / 2}" r="${legacySize / 2}" fill="#fff"/></svg>`,
    );
    const roundBuffer = await sharp(legacyBuffer)
      .composite([{ input: circleMask, blend: "dest-in" }])
      .png()
      .toBuffer();
    writeFileSync(join(mipmapDir, "ic_launcher_round.png"), roundBuffer);

    const foregroundBuffer = await sharp(foregroundSvgBuffer).resize(foregroundSize, foregroundSize).png().toBuffer();
    writeFileSync(join(mipmapDir, "ic_launcher_foreground.png"), foregroundBuffer);

    console.log(`generated mipmap-${density} launcher icons (${legacySize}px / ${foregroundSize}px)`);
  }
}

async function generateSplashScreens() {
  const foregroundSvgBuffer = readFileSync(foregroundSvgPath);

  for (const [dir, { w, h }] of Object.entries(splashSizes)) {
    const outDir = join(resDir, dir);
    mkdirSync(outDir, { recursive: true });

    const symbolSize = Math.round(Math.min(w, h) * 0.42);
    const symbolBuffer = await sharp(foregroundSvgBuffer).resize(symbolSize, symbolSize).png().toBuffer();

    const buffer = await sharp({
      create: { width: w, height: h, channels: 4, background: SPLASH_BG },
    })
      .composite([
        {
          input: symbolBuffer,
          left: Math.round((w - symbolSize) / 2),
          top: Math.round((h - symbolSize) / 2),
        },
      ])
      .png()
      .toBuffer();

    writeFileSync(join(outDir, "splash.png"), buffer);
    console.log(`generated ${dir}/splash.png (${w}x${h})`);
  }
}

async function main() {
  await generateWebIcons();
  await generateAndroidLauncherIcons();
  await generateSplashScreens();
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
