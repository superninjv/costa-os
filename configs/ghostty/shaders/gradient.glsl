// Costa — dramatic animated aurora background
// Deep Mediterranean palette with flowing aurora-like ribbons

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;

    // Sample the terminal content
    vec4 terminal = texture(iChannel0, uv);

    // Costa palette — rich, saturated
    vec3 deep_sea   = vec3(0.20, 0.52, 0.62);   // teal
    vec3 dusk       = vec3(0.48, 0.30, 0.58);   // lavender
    vec3 ember      = vec3(0.62, 0.40, 0.30);   // terracotta
    vec3 shore      = vec3(0.32, 0.58, 0.50);   // sea foam
    vec3 sand       = vec3(0.70, 0.58, 0.36);   // golden sand
    vec3 coral      = vec3(0.62, 0.33, 0.33);   // soft coral
    vec3 midnight   = vec3(0.08, 0.09, 0.14);   // deep base

    // Slow drift — full cycle ~20 seconds
    float t = iTime * 0.05;

    // Aurora ribbons — horizontal bands that undulate vertically
    float ribbon1 = sin(uv.x * 4.0 + t * 3.0 + sin(uv.y * 3.0 + t) * 1.5) * 0.5 + 0.5;
    float ribbon2 = sin(uv.x * 3.0 - t * 2.2 + cos(uv.y * 2.0 - t * 0.8) * 2.0) * 0.5 + 0.5;
    float ribbon3 = sin(uv.x * 5.0 + t * 1.6 + sin(uv.y * 4.0 + t * 1.3) * 1.2) * 0.5 + 0.5;

    // Vertical position modulation — aurora concentrates in bands
    float band1 = exp(-pow((uv.y - 0.3 - sin(t * 0.7) * 0.15) * 4.0, 2.0));
    float band2 = exp(-pow((uv.y - 0.6 + cos(t * 0.5) * 0.12) * 3.5, 2.0));
    float band3 = exp(-pow((uv.y - 0.8 - sin(t * 0.9 + 1.0) * 0.1) * 5.0, 2.0));

    // Combine ribbons with bands for aurora effect
    float aurora1 = ribbon1 * band1;
    float aurora2 = ribbon2 * band2;
    float aurora3 = ribbon3 * band3;

    // Color cycling
    float phase = fract(t * 0.3);
    vec3 col1 = mix(deep_sea, shore, phase);
    vec3 col2 = mix(dusk, ember, phase);
    vec3 col3 = mix(sand, coral, phase);

    // Build the aurora gradient
    vec3 aurora = midnight;
    aurora += col1 * aurora1 * 0.8;
    aurora += col2 * aurora2 * 0.7;
    aurora += col3 * aurora3 * 0.5;

    // Subtle overall gradient from dark bottom to slightly lighter top
    aurora += mix(vec3(0.0), deep_sea * 0.15, uv.y * 0.5);

    // Add slow-moving noise-like texture via layered sines
    float noise = sin(uv.x * 12.0 + t * 4.0) * sin(uv.y * 10.0 - t * 3.0) * 0.02;
    aurora += noise;

    // Vignette — darken edges for depth
    vec2 vig = uv - 0.5;
    float vignette = 1.0 - dot(vig, vig) * 0.8;
    aurora *= vignette;

    // Detect background pixels (close to base color #1b1d2b)
    vec3 base = vec3(0.106, 0.114, 0.169);
    float dist = distance(terminal.rgb, base);
    float mask = 1.0 - smoothstep(0.0, 0.15, dist);

    // Strong gradient presence on background areas
    vec3 result = mix(terminal.rgb, aurora, mask * 0.75);

    // Subtle glow on text near aurora bands — text picks up ambient color
    float textGlow = (aurora1 + aurora2 + aurora3) * 0.06 * (1.0 - mask);
    result += col1 * textGlow;

    fragColor = vec4(result, terminal.a);
}
