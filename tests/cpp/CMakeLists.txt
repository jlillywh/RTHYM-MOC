include(FetchContent)

FetchContent_Declare(
    doctest
    GIT_REPOSITORY https://github.com/doctest/doctest.git
    GIT_TAG v2.4.11
)
FetchContent_MakeAvailable(doctest)

add_executable(rthym_core_tests
    test_core.cpp
    "${RTHYM_SOLVER_SOURCE}"
)

target_link_libraries(rthym_core_tests PRIVATE rthym_core doctest::doctest)
target_compile_options(rthym_core_tests PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Wall -Wextra -O2>
)

add_test(NAME rthym_core_tests COMMAND rthym_core_tests)
