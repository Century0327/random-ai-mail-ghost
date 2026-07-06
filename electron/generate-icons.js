const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

function createPNG(width, height, r, g, b, a = 255) {
    const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

    function crc32(buf) {
        let crc = 0xffffffff;
        const table = [];
        for (let n = 0; n < 256; n++) {
            let c = n;
            for (let k = 0; k < 8; k++) {
                c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
            }
            table[n] = c >>> 0;
        }
        for (let i = 0; i < buf.length; i++) {
            crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
        }
        return (crc ^ 0xffffffff) >>> 0;
    }

    function chunk(type, data) {
        const len = Buffer.alloc(4);
        len.writeUInt32BE(data.length, 0);
        const typeBuf = Buffer.from(type, 'ascii');
        const crcBuf = Buffer.alloc(4);
        crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
        return Buffer.concat([len, typeBuf, data, crcBuf]);
    }

    const ihdr = Buffer.alloc(13);
    ihdr.writeUInt32BE(width, 0);
    ihdr.writeUInt32BE(height, 4);
    ihdr[8] = 8;
    ihdr[9] = 6;
    ihdr[10] = 0;
    ihdr[11] = 0;
    ihdr[12] = 0;

    const rawData = [];
    for (let y = 0; y < height; y++) {
        rawData.push(0);
        for (let x = 0; x < width; x++) {
            const cx = x - width / 2;
            const cy = y - height / 2;
            const dist = Math.sqrt(cx * cx + cy * cy);
            const radius = Math.min(width, height) / 2 - 2;
            if (dist < radius) {
                rawData.push(r, g, b, a);
            } else {
                rawData.push(0, 0, 0, 0);
            }
        }
    }

    const idat = zlib.deflateSync(Buffer.from(rawData));

    return Buffer.concat([
        signature,
        chunk('IHDR', ihdr),
        chunk('IDAT', idat),
        chunk('IEND', Buffer.alloc(0))
    ]);
}

const assetsDir = path.join(__dirname, 'assets');

const icon512 = createPNG(512, 512, 147, 112, 219);
const icon256 = createPNG(256, 256, 147, 112, 219);
const icon128 = createPNG(128, 128, 147, 112, 219);
const icon64 = createPNG(64, 64, 147, 112, 219);
const icon32 = createPNG(32, 32, 147, 112, 219);
const icon16 = createPNG(16, 16, 147, 112, 219);

fs.writeFileSync(path.join(assetsDir, 'icon.png'), icon512);
fs.writeFileSync(path.join(assetsDir, 'icon-512.png'), icon512);
fs.writeFileSync(path.join(assetsDir, 'icon-256.png'), icon256);
fs.writeFileSync(path.join(assetsDir, 'icon-128.png'), icon128);
fs.writeFileSync(path.join(assetsDir, 'icon-64.png'), icon64);
fs.writeFileSync(path.join(assetsDir, 'icon-32.png'), icon32);
fs.writeFileSync(path.join(assetsDir, 'icon-16.png'), icon16);
fs.writeFileSync(path.join(assetsDir, 'tray.png'), icon32);

console.log('Icons generated successfully!');
console.log('  - icon.png (512x512)');
console.log('  - tray.png (32x32)');
console.log('  - and more sizes');
