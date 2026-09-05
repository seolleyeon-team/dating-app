import sharp from "sharp";

// Defense in depth above the patched sharp baseline: these formats are not
// part of the Functions image contract, so keep their native loaders disabled.
sharp.block({
  operation: [
    "VipsForeignLoadNsgif",
    "VipsForeignLoadTiff",
    "VipsForeignLoadVips",
  ],
});
