{
  description = "Narrate a directory tree, get it on disk: voice -> ASR -> json2dir scheme";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      packages = forAllSystems (pkgs:
        let
          python = pkgs.python3Packages;
        in
        {
          default = python.buildPythonApplication {
            pname = "voice2dir";
            version = "0.1.0";
            src = self;
            pyproject = true;
            build-system = [ python.setuptools ];
            # ASR and audio I/O are external tools resolved from PATH.
            nativeBuildInputs = [ pkgs.makeWrapper ];
            postInstall = ''
              wrapProgram $out/bin/voice2dir --prefix PATH : ${
                pkgs.lib.makeBinPath [ pkgs.ffmpeg pkgs.whisper-cpp ]
              }
            '';
            meta = {
              description = "Narrate a directory tree, get it on disk (voice -> ASR -> json2dir scheme)";
              homepage = "https://github.com/71g3pf4c3/voice2dir";
              license = pkgs.lib.licenses.gpl3Only;
              mainProgram = "voice2dir";
            };
          };
        });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: [ ]))
            pkgs.ffmpeg
            pkgs.whisper-cpp
            pkgs.espeak-ng
          ];
        };
      });
    };
}
