# sanity_check.py
import os
from dom_scanner import RepoDOMScanner


def run_test():
    print("Booting DOM Scanner Sanity Check...")

    # Initialize the scanner on your current project root
    scanner = RepoDOMScanner(root_dir=".")
    scanner.build_dom()

    # Scan the resulting map for anything that shouldn't be there
    invalid_files_found = []
    for path in scanner.dom_map.values():
        filename = os.path.basename(path)  # OS-agnostic filename extraction
        is_binary = filename.endswith(('.class', '.pyc', '.exe', '.dll'))
        is_hidden = filename.startswith('.')

        if is_binary or is_hidden:
            invalid_files_found.append(path)

    print(f"Total valid source files mapped: {len(scanner.dom_map)}")

    if invalid_files_found:
        print(f"\n❌ FAILED: Found {len(invalid_files_found)} invalid files slipping through!")
        for f in invalid_files_found[:10]:  # Print first 10 offenders
            print(f"  - {f}")
    else:
        print("\n✅ SUCCESS: Zero binary, compiled, or hidden files detected in the DOM map.")
        print("The JIT Memory context is safe.")


if __name__ == "__main__":
    run_test()